-- On-demand refresh tag: a single-series refresh of a ecbwatch series selects
-- this model with its downstream graph (see orchestration/ops.py).
{{ config(tags=['ops_refresh_ecbwatch']) }}
-- Staging: explode the ecb-watch.eu feed (raw.source_fetch.payload) into one row
-- per (fetch, meeting, scenario).
--
-- The payload is a single nested document, not an observation list:
--
--   {"abs_data": {"2026-10-29": {"2.50%": 0.5, "2.75%": 0.5, "3.00%": 0.0},
--                 "2026-12-17": {...}},
--    "current_rate": 2.5,
--    "metadata": {"last_updated": "2026-09-21", "version": "3.0.0",
--                 "status": "active", "data_sources": "EMP futures (primary), ..."}}
--
-- so the generic observation parsers do not apply. Two unnest steps: the outer
-- `abs_data` object is keyed by meeting date, the inner object by rate string.
-- Rate keys are parsed from "2.50%" to 2.50 (percent) and probabilities are
-- kept as fractions, matching fct_macro_* and the local engine respectively.
--
-- Every fetch vintage is retained (with fetched_at) so the drift in market
-- expectations over time stays queryable; downstream takes the newest batch.
-- `source_*` columns are the feed's own provenance and are exposed so the
-- dashboard can show how stale and how trustworthy the cross-check is.
with src as (
    select
        resource as series_id,
        fetched_at,
        payload as doc
    from {{ source('raw', 'source_fetch') }}
    where source = 'ecbwatch'
      and payload is not null
      and payload -> 'abs_data' is not null
),

meetings as (
    select
        s.series_id,
        s.fetched_at,
        nullif(s.doc ->> 'current_rate', '')::numeric          as current_rate,
        s.doc -> 'metadata' ->> 'last_updated'                 as source_last_updated,
        s.doc -> 'metadata' ->> 'version'                      as source_version,
        s.doc -> 'metadata' ->> 'status'                       as source_status,
        s.doc -> 'metadata' ->> 'data_sources'                 as source_data_sources,
        meeting.key                                            as meeting_date_raw,
        meeting.value                                          as scenarios
    from src s,
         jsonb_each(s.doc -> 'abs_data') as meeting
),

exploded as (
    select
        m.series_id,
        m.fetched_at,
        m.current_rate,
        m.source_last_updated,
        m.source_version,
        m.source_status,
        m.source_data_sources,
        (m.meeting_date_raw)::date                                    as meeting_date,
        replace(scenario.key, '%', '')::numeric                       as scenario_rate,
        nullif(scenario.value, '')::numeric                           as probability
    from meetings m,
         jsonb_each_text(m.scenarios) as scenario
    -- guard the numeric cast: a non-numeric rate key must not abort the build
    where scenario.key ~ '^[0-9]+(\.[0-9]+)?%$'
)

select
    series_id,
    meeting_date,
    scenario_rate,
    probability,
    current_rate,
    source_last_updated,
    source_version,
    source_status,
    source_data_sources,
    fetched_at::date as known_at,
    fetched_at
from exploded
where scenario_rate is not null
