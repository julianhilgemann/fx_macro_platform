-- Singular test: grains must never be finer than the series' native
-- frequency. A weekly series may not appear at the day grain, a monthly
-- series not at day/week, a quarterly series only at quarter/year.
with violations as (
    select
        g.series_id,
        g.grain,
        s.frequency as native_frequency
    from {{ ref('fct_macro_series_grains') }} g
    join {{ ref('dim_series') }} s using (series_id)
    where (s.frequency = 'W' and g.grain = 'day')
       or (s.frequency = 'M' and g.grain in ('day', 'week'))
       or (s.frequency = 'Q' and g.grain in ('day', 'week', 'month'))
)

select * from violations
