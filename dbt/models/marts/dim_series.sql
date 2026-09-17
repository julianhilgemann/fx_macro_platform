-- Rebuilt by the single-series refresh path (tag:ops_refresh).
{{ config(tags=['ops_refresh']) }}
-- Series catalog dimension (spec §7). Served by the API/BI alongside the facts.
select * from {{ ref('series_catalog') }}
