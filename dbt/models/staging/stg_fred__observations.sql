-- On-demand refresh tag: a single-series refresh of a fred series selects this
-- model with its downstream graph (see orchestration/ops.py).
{{ config(tags=['ops_refresh_fred']) }}
-- Staging: parse the FRED fetch payload (jsonb) into typed observations.
-- known_at = the observation's realtime_start (release/vintage date);
-- fetched_at = provenance (when we pulled it).
with src as (
    select
        resource as series_id,
        fetched_at,
        payload -> 'observations' as obs
    from {{ source('raw', 'source_fetch') }}
    where source = 'fred'
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
    coalesce((o ->> 'realtime_start')::date, fetched_at::date) as known_at,
    fetched_at
from flat
where o ->> 'date' is not null
