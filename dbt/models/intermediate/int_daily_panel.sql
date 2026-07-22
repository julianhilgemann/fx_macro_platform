-- Daily EUR/USD panel: pivot each series onto its stable column, align to a daily
-- calendar spine, carry the last known value forward (macro series are step
-- functions from their known date), and compute differentials + curve slopes.
--
-- This is the one place series_id -> panel column is hardcoded. Keep in sync with
-- the `role` field in ingest/config.py.
with latest as (
    select * from {{ ref('int_series_latest_vintage') }}
),

pivoted as (
    select
        reference_period as d,
        -- spot + FX context (fred)
        max(case when series_id = 'DEXUSEU'  then value end) as eurusd_spot,
        max(case when series_id = 'DTWEXBGS' then value end) as usd_broad_index,
        max(case when series_id = 'VIXCLS'   then value end) as vix,
        -- US policy corridor (fred)
        max(case when series_id = 'FEDFUNDS' then value end) as fed_funds_rate,
        max(case when series_id = 'DFEDTARU' then value end) as fed_target_upper,
        max(case when series_id = 'DFEDTARL' then value end) as fed_target_lower,
        -- ECB policy corridor: DFR (fred) + MRO/MLF (ecb sdw)
        max(case when series_id = 'ECBDFR'   then value end) as ecb_policy_rate,
        max(case when series_id = 'ECB_MRO'  then value end) as ecb_mro_rate,
        max(case when series_id = 'ECB_MLF'  then value end) as ecb_mlf_rate,
        -- US Treasury yields (fred)
        max(case when series_id = 'DGS2'     then value end) as us_2y,
        max(case when series_id = 'DGS10'    then value end) as us_10y,
        -- German Bund yields (bundesbank)
        max(case when series_id = 'DE2Y'     then value end) as de_2y,
        max(case when series_id = 'DE10Y'    then value end) as de_10y
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
    select s.d, p.* exclude (d)
    from spine s
    left join pivoted p on p.d = s.d
),

-- Carry the last known value forward (step functions / weekend & holiday gaps).
filled as (
    select
        d,
        last_value(eurusd_spot      ignore nulls) over w as eurusd_spot,
        last_value(usd_broad_index  ignore nulls) over w as usd_broad_index,
        last_value(vix              ignore nulls) over w as vix,
        last_value(fed_funds_rate   ignore nulls) over w as fed_funds_rate,
        last_value(fed_target_upper ignore nulls) over w as fed_target_upper,
        last_value(fed_target_lower ignore nulls) over w as fed_target_lower,
        last_value(ecb_policy_rate  ignore nulls) over w as ecb_policy_rate,
        last_value(ecb_mro_rate     ignore nulls) over w as ecb_mro_rate,
        last_value(ecb_mlf_rate     ignore nulls) over w as ecb_mlf_rate,
        last_value(us_2y            ignore nulls) over w as us_2y,
        last_value(us_10y           ignore nulls) over w as us_10y,
        last_value(de_2y            ignore nulls) over w as de_2y,
        last_value(de_10y           ignore nulls) over w as de_10y
    from joined
    window w as (order by d rows between unbounded preceding and current row)
)

select
    d as reference_period,
    eurusd_spot,
    usd_broad_index,
    vix,
    -- ECB corridor (ceiling / mid / floor)
    ecb_mlf_rate,
    ecb_mro_rate,
    ecb_policy_rate,
    -- Fed corridor (range + effective)
    fed_target_upper,
    fed_target_lower,
    fed_funds_rate,
    -- yield legs
    us_2y,
    us_10y,
    de_2y,
    de_10y,
    -- differentials (US minus Germany; positive = US yields higher) & curve slopes
    us_2y  - de_2y                    as diff_2y,
    us_10y - de_10y                   as diff_10y,
    us_10y - us_2y                    as us_2s10s,
    de_10y - de_2y                    as de_2s10s,
    fed_funds_rate - ecb_policy_rate  as policy_rate_spread
from filled
order by d
