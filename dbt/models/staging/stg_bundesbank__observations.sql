-- Staging: parse the Bundesbank BBSSY fetch payload (normalized jsonb).
-- Bundesbank exposes no vintage; known_at = fetched_at::date.
with src as (
    select
        resource as series_id,
        fetched_at,
        payload -> 'observations' as obs
    from {{ source('raw', 'source_fetch') }}
    where source = 'bundesbank'
      and payload is not null
),

flat as (
    select
        series_id,
        fetched_at,
        jsonb_array_elements(obs) as o
    from src
)

select
    series_id,
    (o ->> 'date')::date as obs_date,
    case
        when o ->> 'value' is null or o ->> 'value' = '.' then null
        else (o ->> 'value')::numeric
    end as value,
    fetched_at::date as known_at,
    fetched_at
from flat
where o ->> 'date' is not null
