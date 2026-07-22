-- Vintage resolution: for each (series_id, reference_period) keep the value from
-- the most recent fetch (latest known revision). Missing observations dropped.
with obs as (
    select *
    from {{ ref('stg_fred__observations') }}
    where value is not null
)

select
    source,
    series_id,
    reference_period,
    value,
    fetch_timestamp
from obs
qualify row_number() over (
    partition by series_id, reference_period
    order by fetch_timestamp desc
) = 1
