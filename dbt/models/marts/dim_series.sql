-- Series catalog dimension (spec §7). Served by the API/BI alongside the facts.
select * from {{ ref('series_catalog') }}
