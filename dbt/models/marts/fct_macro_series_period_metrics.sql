-- Wide period-metrics mart: one row per (series_id, grain, period_date) with
-- the level plus period-over-period (MoM), quarter-ago (QoQ), year-ago (YoY),
-- month-to-date and year-to-date % changes.
--
-- Offsets are grain-aware:
--   mom_pct  previous period (lag 1) for every grain
--   qoq_pct  -3 months (day/month/quarter), -13 weeks (week); null for year
--   yoy_pct  -1 year on clamped calendar dates; -52 weeks (364 days) for week
--   mtd_pct  vs the last period of the previous month
--   ytd_pct  vs the last period of the previous year
--
-- Everything is set-based (equi/hash joins over pre-aggregated month/year
-- boundary tables) — deliberately no LATERAL per-row lookups: Postgres 16's
-- Memoize executor degrades to a linear cache scan on large key spaces and
-- made the previous lateral version run for minutes instead of seconds.

with base as (
    select
        series_id,
        grain,
        period_date,
        value
    from {{ ref('fct_macro_series_grains') }}
),

with_prev as (
    select
        series_id,
        grain,
        period_date,
        value,
        lag(value) over w as prev_value
    from base
    window w as (partition by series_id, grain order by period_date)
),

month_last as (
    select
        series_id,
        grain,
        date_trunc('month', period_date)::date as month_key,
        max(period_date) as last_period
    from base
    group by series_id, grain, date_trunc('month', period_date)::date
),

year_last as (
    select
        series_id,
        grain,
        date_trunc('year', period_date)::date as year_key,
        max(period_date) as last_period
    from base
    group by series_id, grain, date_trunc('year', period_date)::date
)

select
    b.series_id,
    b.grain,
    b.period_date,
    b.value,
    (b.value / nullif(b.prev_value, 0) - 1) * 100 as mom_pct,
    (b.value / nullif(q.value, 0) - 1) * 100 as qoq_pct,
    (b.value / nullif(y.value, 0) - 1) * 100 as yoy_pct,
    (b.value / nullif(m.value, 0) - 1) * 100 as mtd_pct,
    (b.value / nullif(ytd.value, 0) - 1) * 100 as ytd_pct
from with_prev b
left join base q
    on q.series_id = b.series_id
   and q.grain = b.grain
   and b.grain in ('day', 'week', 'month', 'quarter')
   and q.period_date = b.period_date - case b.grain
         when 'week' then interval '91 days'
         else interval '3 months'
       end
left join base y
    on y.series_id = b.series_id
   and y.grain = b.grain
   and y.period_date = b.period_date - case b.grain
         when 'week' then interval '364 days'
         else interval '1 year'
       end
left join month_last ml
    on ml.series_id = b.series_id
   and ml.grain = b.grain
   and ml.month_key = date_trunc('month', b.period_date)::date - interval '1 month'
left join base m
    on m.series_id = ml.series_id
   and m.grain = ml.grain
   and m.period_date = ml.last_period
left join year_last yl
    on yl.series_id = b.series_id
   and yl.grain = b.grain
   and yl.year_key = date_trunc('year', b.period_date)::date - interval '1 year'
left join base ytd
    on ytd.series_id = yl.series_id
   and ytd.grain = yl.grain
   and ytd.period_date = yl.last_period
