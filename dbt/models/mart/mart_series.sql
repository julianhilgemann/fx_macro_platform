-- Long-format latest-vintage values for single-series API reads. API contract.
select
    series_id,
    reference_period,
    value
from {{ ref('int_series_latest_vintage') }}
order by series_id, reference_period
