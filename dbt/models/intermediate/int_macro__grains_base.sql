-- Resample every series onto each applicable calendar grain (never finer than
-- the native frequency) using last-observation-in-period (asof) semantics.
--
-- Grains:
--   day     calendar-filled daily grid (only for D-frequency series)
--   week    date_trunc('week') buckets (ISO weeks starting Monday)
--   month   date_trunc('month') buckets
--   quarter date_trunc('quarter') buckets
--   year    date_trunc('year') buckets
--
-- Coarser grains pick the last observation inside each bucket, so a monthly
-- bucket holds the month-end (asof) value even for daily series.

with obs as (
    select
        o.series_id,
        o.obs_date,
        o.value,
        coalesce(s.frequency, 'D') as frequency
    from {{ ref('fct_macro_observation_latest') }} o
    left join {{ ref('dim_series') }} s using (series_id)
),

-- ------------------------------------------------------------------ day grain
bounds as (
    select
        series_id,
        min(obs_date) as lo,
        max(obs_date) as hi
    from obs
    where frequency = 'D'
    group by series_id
),

calendar as (
    select
        b.series_id,
        g.d::date as obs_date
    from bounds b
    cross join lateral generate_series(b.lo, b.hi, interval '1 day') as g(d)
),

day_joined as (
    select
        c.series_id,
        c.obs_date,
        o.value
    from calendar c
    left join obs o
        on o.series_id = c.series_id
       and o.obs_date = c.obs_date
),

day_grp as (
    select
        series_id,
        obs_date,
        value,
        count(value) over (partition by series_id order by obs_date) as value_grp
    from day_joined
),

day_filled as (
    select
        series_id,
        'day' as grain,
        obs_date as period_date,
        first_value(value) over (
            partition by series_id, value_grp
            order by obs_date
        ) as value
    from day_grp
),

-- ------------------------------------------------------------ coarser grains
bucketed as (
    select
        series_id,
        'week' as grain,
        date_trunc('week', obs_date)::date as period_date,
        value,
        obs_date
    from obs
    where frequency in ('D', 'W')

    union all

    select
        series_id,
        'month' as grain,
        date_trunc('month', obs_date)::date as period_date,
        value,
        obs_date
    from obs
    where frequency in ('D', 'W', 'M')

    union all

    select
        series_id,
        'quarter' as grain,
        date_trunc('quarter', obs_date)::date as period_date,
        value,
        obs_date
    from obs
    where frequency in ('D', 'W', 'M', 'Q')

    union all

    select
        series_id,
        'year' as grain,
        date_trunc('year', obs_date)::date as period_date,
        value,
        obs_date
    from obs
),

last_in_bucket as (
    select distinct on (series_id, grain, period_date)
        series_id,
        grain,
        period_date,
        value,
        obs_date
    from bucketed
    order by series_id, grain, period_date, obs_date desc
)

-- ------------------------------------------------------------------- union
select
    series_id,
    grain,
    period_date,
    value
from last_in_bucket

union all

select
    series_id,
    grain,
    period_date,
    value
from day_filled
where value is not null
