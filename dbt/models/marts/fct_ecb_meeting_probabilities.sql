-- Rebuilt by the single-series refresh path (tag:ops_refresh).
{{ config(tags=['ops_refresh']) }}
-- Market-implied ECB rate probabilities from the official euro OIS curve.
--
-- METHOD (the CME FedWatch decomposition, per ecb-watch.eu's own description):
--   1. Take the latest official euro OIS rate per maturity bucket (ECB MMSR,
--      MM_SEGMENT 'O' / DATA_TYPE_MM 'WR').
--   2. A Governing Council decision lands at the *start* of a reserve
--      maintenance period, so the OIS rate at the midpoint of the period
--      [meeting_i, meeting_{i+1}) approximates the average overnight rate
--      expected during that period. Linearly interpolate the bucket curve to
--      that midpoint (clamped at both ends of the curve).
--   3. The expected change at meeting i is the difference between consecutive
--      period rates, with the period before the first meeting anchored on the
--      current deposit facility rate.
--   4. Split each change into adjacent 25bp steps (the same binary
--      decomposition FedWatch uses), then convolve the per-meeting
--      distributions to get the distribution of the rate *level* after each
--      meeting.
--
-- HONEST LIMITS — read before trusting a number:
--   * The input is bucket averages, not a meeting-dated swap curve. MMSR also
--     lags live pricing by roughly six to eight weeks and publishes in coarse
--     steps, so these probabilities are *indicative*. `staleness_days` is
--     carried on every row; check it before drawing conclusions.
--   * The convolution enumerates 2^n paths over the horizon (default 4
--     meetings -> 16 paths), so probabilities are exact given the per-meeting
--     binary split, not a simulation.
--   * For trade-accurate numbers you need dated €STR futures from an exchange.
--     `fct_ecb_probability_crosscheck` scores this engine against ecb-watch.eu,
--     which does exactly that.

with

-- --- 1. the OIS curve ------------------------------------------------------
curve_spec as (
    select * from (values
        ('EA_OIS_1M',  0.083333),
        ('EA_OIS_2M',  0.166667),
        ('EA_OIS_3M',  0.250000),
        ('EA_OIS_6M',  0.500000),
        ('EA_OIS_9M',  0.750000),
        ('EA_OIS_12M', 1.000000),
        ('EA_OIS_2Y',  2.000000)
    ) as t(series_id, tenor_years)
),

curve_obs as (
    select
        c.series_id,
        c.tenor_years,
        o.obs_date,
        o.value
    from curve_spec c
    join {{ ref('fct_macro_observation_latest') }} o
      on o.series_id = c.series_id
),

-- Newest observation per bucket: the curve snapshot the engine runs on.
curve_pts as (
    select distinct on (series_id)
        series_id,
        tenor_years,
        obs_date,
        value
    from curve_obs
    order by series_id, obs_date desc
),

anchor as (
    select
        (select max(obs_date) from curve_pts)                      as curve_as_of,
        (select count(*) from curve_pts)                           as curve_points,
        (select value
           from {{ ref('fct_macro_observation_latest') }}
          where series_id = 'ECB_DFR'
          order by obs_date desc
          limit 1)                                                 as current_rate
),

-- --- 2. meetings and their maintenance-period midpoints --------------------
meetings as (
    select
        meeting_date,
        lead(meeting_date) over (order by meeting_date) as next_meeting_date
    from {{ ref('ecb_meeting_calendar') }}
    where meeting_type = 'monetary_policy'
),

upcoming as (
    select
        meeting_date,
        next_meeting_date,
        row_number() over (order by meeting_date) as meeting_index
    from meetings
    -- Only meetings still ahead of us. A meeting that sits between the curve
    -- snapshot and today has already been decided, and its outcome is already
    -- baked into the deposit facility rate the engine anchors on — including it
    -- would double-count that decision and mis-anchor every later meeting.
    where meeting_date >= current_date
),

targets as (
    select
        u.meeting_date,
        u.meeting_index,
        -- midpoint of the maintenance period that the meeting opens
        u.meeting_date
          + floor((coalesce(u.next_meeting_date, u.meeting_date + 90)
                   - u.meeting_date) / 2.0)::int as period_midpoint,
        (u.meeting_date
          + floor((coalesce(u.next_meeting_date, u.meeting_date + 90)
                   - u.meeting_date) / 2.0)::int
          - a.curve_as_of) / 365.25::numeric as t_years
    from upcoming u
    cross join anchor a
),

-- --- 3. interpolate the curve to each midpoint -----------------------------
bounded as (
    select
        t.*,
        (select p.tenor_years from curve_pts p
          where p.tenor_years <= t.t_years
          order by p.tenor_years desc limit 1) as lo_tenor,
        (select p.tenor_years from curve_pts p
          where p.tenor_years >= t.t_years
          order by p.tenor_years asc limit 1) as hi_tenor
    from targets t
),

resolved as (
    select
        b.*,
        -- clamp to the ends of the curve rather than dropping the meeting
        coalesce(b.lo_tenor, (select min(tenor_years) from curve_pts)) as lo_t,
        coalesce(b.hi_tenor, (select max(tenor_years) from curve_pts)) as hi_t
    from bounded b
),

period_rates as (
    select
        r.meeting_date,
        r.meeting_index,
        r.period_midpoint,
        r.t_years,
        case
            when r.hi_t = r.lo_t then lo.value
            else lo.value
                 + (hi.value - lo.value) * (r.t_years - r.lo_t) / (r.hi_t - r.lo_t)
        end as period_rate
    from resolved r
    join curve_pts lo on lo.tenor_years = r.lo_t
    join curve_pts hi on hi.tenor_years = r.hi_t
),

-- --- 4. per-meeting expected change, split into 25bp steps -----------------
per_meeting as (
    select
        p.meeting_date,
        p.meeting_index,
        p.period_midpoint,
        p.t_years,
        p.period_rate,
        coalesce(lag(p.period_rate) over (order by p.meeting_index),
                 a.current_rate)                        as prev_rate,
        a.current_rate,
        a.curve_as_of,
        (p.period_rate
          - coalesce(lag(p.period_rate) over (order by p.meeting_index),
                     a.current_rate))                   as expected_change_pct
    from period_rates p
    cross join anchor a
),

stepped as (
    select
        m.*,
        -- clamp: a >100bp single-meeting move is not a credible input and would
        -- otherwise blow up the scenario grid
        least(greatest(m.expected_change_pct / 0.25, -4), 4) as steps_raw
    from per_meeting m
),

split as (
    select
        s.*,
        floor(s.steps_raw)::int                     as floor_steps,
        s.steps_raw - floor(s.steps_raw)            as frac,
        -- keep the log-space convolution finite
        least(greatest(s.steps_raw - floor(s.steps_raw), 0.0001), 0.9999) as prob_up
    from stepped s
),

-- --- 5. convolve the per-meeting splits over the horizon -------------------
horizon as (
    select *
    from split
    where meeting_index <= {{ var('ecb_watch_horizon_meetings', 4) }}
),

-- The level distribution *after* meeting k depends only on meetings 1..k, so
-- meeting k enumerates 2^k paths. Enumerating the full 2^N space and summing
-- instead would count each of meeting k's prefixes 2^(N-k) times and inflate
-- that meeting's mass by the same factor — hence the mask space is per-meeting
-- (`k`), not global.
paths as (
    select
        k.meeting_index,
        k.meeting_date,
        m.mask,
        -- cumulative steps and log-probability over meetings 1..k
        sum(h.floor_steps
            + ((m.mask >> ((h.meeting_index - 1)::int)) & 1))       as cum_steps,
        sum(ln(
            case when ((m.mask >> ((h.meeting_index - 1)::int)) & 1) = 1
                 then h.prob_up else 1 - h.prob_up end
        ))                                                          as cum_log_prob
    from horizon k
    cross join lateral (
        select generate_series(
            0, power(2, k.meeting_index::int)::int - 1
        ) as mask
    ) m
    join horizon h
      on h.meeting_index <= k.meeting_index
    group by k.meeting_index, k.meeting_date, m.mask
),

-- --- 6. final shape --------------------------------------------------------
-- exp(cum_log_prob) over the 2^k paths sums to exactly 1 per meeting.
probability_by_meeting as (
    select
        meeting_index,
        meeting_date,
        cum_steps,
        sum(exp(cum_log_prob)) as probability
    from paths
    group by meeting_index, meeting_date, cum_steps
)

select
    'local_ois'                                   as engine,
    p.meeting_index,
    p.meeting_date,
    p.meeting_date - current_date                 as days_to_meeting,
    round(m.current_rate + p.cum_steps * 0.25, 4) as scenario_rate,
    round(p.probability, 6)                       as probability,
    round(m.expected_change_pct * 100, 2)         as expected_change_bp,
    round(m.prob_up, 6)                           as prob_higher_step,
    round(m.current_rate, 4)                      as current_rate,
    m.curve_as_of,
    (current_date - m.curve_as_of)                as staleness_days,
    round(m.period_rate, 4)                       as period_ois_rate,
    m.period_midpoint,
    round(m.t_years, 4)                           as period_midpoint_years
from probability_by_meeting p
join split m
  on m.meeting_index = p.meeting_index
order by p.meeting_index, scenario_rate
