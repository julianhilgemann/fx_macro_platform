-- Latest view (spec §6): one row per (series_id, obs_date), newest known value.
select
    md5(concat_ws('|', series_id, cast(obs_date as varchar))) as series_obs_key,
    series_id,
    obs_date,
    known_at,
    value
from {{ ref('int_macro__observations_unioned') }}
where is_latest
