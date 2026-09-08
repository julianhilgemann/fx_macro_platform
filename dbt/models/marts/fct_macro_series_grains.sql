-- Resampled grains mart (table). One row per (series_id, grain, period_date),
-- values follow last-observation-in-period semantics. Grains are never finer
-- than the series' native frequency (asserted by a singular test) and range
-- from day (calendar-filled, D-frequency series only) up to year.
select
    series_id,
    grain,
    period_date,
    value
from {{ ref('int_macro__grains_base') }}
