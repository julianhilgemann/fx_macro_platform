-- Long-format transforms mart: one row per
-- (series_id, grain, period_date, transform).
--
-- Transforms (Signal Lab runtime moved into SQL):
--   level       raw value
--   diff        value - previous period value
--   pct_change  (value / prev - 1) * 100
--   log_level   ln(value), positive values only
--   log_return  (ln(value) - ln(prev)) * 100, positive values only
--   index_100   value / first value of the series * 100 (base = inception)
--   zscore      (value - mean) / stddev over the full series-grain history
--
-- STL-based components (trend/seasonal/residual/seasonally-adjusted) are NOT
-- included: Loess smoothing has no SQL equivalent, so the dashboard still
-- computes those at runtime.

with base as (
    select
        series_id,
        grain,
        period_date,
        value
    from {{ ref('fct_macro_series_grains') }}
),

windowed as (
    select
        series_id,
        grain,
        period_date,
        value,
        lag(value) over w as prev_value,
        first_value(value) over w as first_val,
        avg(value) over w as mean_value,
        stddev_samp(value) over w as sd_value
    from base
    window w as (partition by series_id, grain order by period_date)
),

transforms as (
    select series_id, grain, period_date, 'level' as transform, value
    from windowed

    union all

    select series_id, grain, period_date, 'diff' as transform, value - prev_value
    from windowed
    where prev_value is not null

    union all

    select series_id, grain, period_date, 'pct_change' as transform,
           (value / nullif(prev_value, 0) - 1) * 100
    from windowed
    where prev_value is not null

    union all

    select series_id, grain, period_date, 'log_level' as transform, ln(value)
    from windowed
    where value > 0

    union all

    select series_id, grain, period_date, 'log_return' as transform,
           (ln(value) - ln(prev_value)) * 100
    from windowed
    where value > 0 and prev_value > 0

    union all

    select series_id, grain, period_date, 'index_100' as transform,
           value / nullif(first_val, 0) * 100
    from windowed
    where first_val is not null

    union all

    select series_id, grain, period_date, 'zscore' as transform,
           (value - mean_value) / nullif(sd_value, 0)
    from windowed
    where sd_value > 0
)

select
    series_id,
    grain,
    period_date,
    transform,
    value
from transforms
where value is not null
