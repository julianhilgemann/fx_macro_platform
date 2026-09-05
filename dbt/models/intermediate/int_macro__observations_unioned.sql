-- Union the three source stagings and resolve to a unique bitemporal grain
-- (series_id, obs_date, known_at). is_latest marks the newest known value per
-- (series_id, obs_date). Missing values are dropped (the fact has no nulls).
with unioned as (
    select * from {{ ref('stg_fred__observations') }}
    union all
    select * from {{ ref('stg_ecb__observations') }}
    union all
    select * from {{ ref('stg_bundesbank__observations') }}
),

deduped as (
    select
        series_id,
        obs_date,
        known_at,
        value,
        fetched_at,
        row_number() over (
            partition by series_id, obs_date, known_at
            order by fetched_at desc
        ) as rn
    from unioned
    where value is not null
)

select
    series_id,
    obs_date,
    known_at,
    value,
    fetched_at,
    row_number() over (
        partition by series_id, obs_date
        order by known_at desc, fetched_at desc
    ) = 1 as is_latest
from deduped
where rn = 1
