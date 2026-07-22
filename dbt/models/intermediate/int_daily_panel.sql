-- Daily EUR/USD panel: pivot each series onto its stable column, align to a daily
-- calendar spine, carry the last known value forward (macro series are step
-- functions from their known date), and compute the Bund-Treasury differentials.
--
-- This is the one place series_id -> panel column is hardcoded. Keep in sync with
-- the `role` field in ingest/config.py.
with latest as (
    select * from {{ ref('int_series_latest_vintage') }}
),

pivoted as (
    select
        reference_period as d,
        max(case when series_id = 'DEXUSEU'  then value end) as eurusd_spot,      -- fred
        max(case when series_id = 'FEDFUNDS' then value end) as fed_funds_rate,   -- fred
        max(case when series_id = 'ECBDFR'   then value end) as ecb_policy_rate,  -- fred
        max(case when series_id = 'DGS2'     then value end) as us_2y,            -- fred
        max(case when series_id = 'DGS10'    then value end) as us_10y,           -- fred
        max(case when series_id = 'DE2Y'     then value end) as de_2y,            -- bundesbank
        max(case when series_id = 'DE10Y'    then value end) as de_10y            -- bundesbank
    from latest
    group by 1
),

bounds as (
    select min(d) as start_date, max(d) as end_date from pivoted
),

spine as (
    select cast(unnest(generate_series(
        (select start_date from bounds)::timestamp,
        (select end_date   from bounds)::timestamp,
        interval 1 day
    )) as date) as d
),

joined as (
    select
        s.d,
        p.eurusd_spot, p.ecb_policy_rate, p.fed_funds_rate,
        p.us_2y, p.us_10y, p.de_2y, p.de_10y
    from spine s
    left join pivoted p on p.d = s.d
),

filled as (
    select
        d,
        last_value(eurusd_spot     ignore nulls) over w as eurusd_spot,
        last_value(ecb_policy_rate ignore nulls) over w as ecb_policy_rate,
        last_value(fed_funds_rate  ignore nulls) over w as fed_funds_rate,
        last_value(us_2y           ignore nulls) over w as us_2y,
        last_value(us_10y          ignore nulls) over w as us_10y,
        last_value(de_2y           ignore nulls) over w as de_2y,
        last_value(de_10y          ignore nulls) over w as de_10y
    from joined
    window w as (order by d rows between unbounded preceding and current row)
)

select
    d as reference_period,
    eurusd_spot,
    ecb_policy_rate,
    fed_funds_rate,
    us_2y,
    us_10y,
    de_2y,
    de_10y,
    -- Differentials are US minus Germany (Treasury - Bund); positive = US yields higher.
    us_2y  - de_2y                    as diff_2y,
    us_10y - de_10y                   as diff_10y,
    fed_funds_rate - ecb_policy_rate  as policy_rate_spread
from filled
order by d
