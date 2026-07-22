-- Curated daily EUR/USD + policy-corridor + differential panel. This shape is the
-- API contract; the column list/order is defined by int_daily_panel's final select.
select * from {{ ref('int_daily_panel') }}
