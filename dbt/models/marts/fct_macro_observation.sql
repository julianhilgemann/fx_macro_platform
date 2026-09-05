-- Bitemporal fact (spec §6): grain (series_id, obs_date, known_at).
select
    md5(concat_ws('|', series_id, cast(obs_date as varchar), cast(known_at as varchar))) as observation_key,
    series_id,
    obs_date,
    known_at,
    value,
    is_latest
from {{ ref('int_macro__observations_unioned') }}
