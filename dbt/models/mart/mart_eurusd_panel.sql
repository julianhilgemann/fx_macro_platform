-- Curated daily EUR/USD + differential panel. This shape is the API contract:
-- upstream may be refactored freely, these columns should stay stable.
select
    reference_period,
    eurusd_spot,
    ecb_policy_rate,
    fed_funds_rate,
    us_2y,
    us_10y,
    de_2y,
    de_10y,
    diff_2y,
    diff_10y,
    policy_rate_spread
from {{ ref('int_daily_panel') }}
