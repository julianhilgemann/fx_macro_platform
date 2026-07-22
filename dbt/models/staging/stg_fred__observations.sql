-- Staging: 1:1 with raw. Type-cast, add a surrogate grain key, rename. No logic.
with source as (
    select * from {{ source('raw', 'raw_observations') }}
)

select
    md5(concat_ws('|',
        source,
        series_id,
        cast(reference_period as varchar),
        cast(fetch_timestamp as varchar)
    ))                                  as observation_key,
    source,
    series_id,
    cast(reference_period as date)      as reference_period,
    cast(value as double)               as value,
    cast(fetch_timestamp as timestamp)  as fetch_timestamp,
    raw_file,
    loaded_at
from source
