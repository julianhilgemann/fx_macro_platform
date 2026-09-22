-- Rebuilt by the single-series refresh path (tag:ops_refresh).
{{ config(tags=['ops_refresh']) }}
-- Cross-check: the local OIS-implied engine scored against ecb-watch.eu.
--
-- This is the point of ingesting a third-party feed. ecb-watch decomposes
-- *dated €STR futures* — the trade-accurate input we cannot get from an
-- official API — while `fct_ecb_meeting_probabilities` interpolates the ECB
-- MMSR OIS bucket curve. Putting them side by side on the same (meeting,
-- scenario) grid turns "our approximation is a bit stale" into a number:
--
--   * `diff_pp`             — local minus ecb-watch, in percentage points;
--   * `total_variation_pp`  — 0.5 * Σ|Δ| over the meeting's scenarios: the
--                             total probability mass that would have to move to
--                             turn one distribution into the other. 0.0 = the two
--                             engines agree exactly; 100 = they disagree
--                             completely. Treat this as the headline accuracy
--                             metric for the local engine.
--
-- Rows appear for scenarios present in only one engine (matched = false); that
-- is itself a finding — usually the local curve is too stale to see a scenario
-- the futures market is already pricing.
with watch_latest as (
    select
        meeting_date,
        scenario_rate,
        probability,
        current_rate,
        source_last_updated,
        source_version,
        source_status,
        source_data_sources,
        known_at
    from {{ ref('stg_ecbwatch__probabilities') }}
    where fetched_at = (
        select max(fetched_at) from {{ ref('stg_ecbwatch__probabilities') }}
    )
),

local as (
    select
        meeting_date,
        scenario_rate,
        probability
    from {{ ref('fct_ecb_meeting_probabilities') }}
),

joined as (
    select
        coalesce(l.meeting_date, w.meeting_date)     as meeting_date,
        coalesce(l.scenario_rate, w.scenario_rate)   as scenario_rate,
        l.probability                                as local_probability,
        w.probability                                as ecbwatch_probability,
        w.current_rate                               as ecbwatch_current_rate,
        w.source_last_updated,
        w.source_version,
        w.source_status,
        w.source_data_sources,
        w.known_at                                   as ecbwatch_known_at
    from local l
    full outer join watch_latest w
      on w.meeting_date = l.meeting_date
     and w.scenario_rate = l.scenario_rate
),

scored as (
    select
        j.*,
        (j.local_probability - j.ecbwatch_probability) * 100 as diff_pp,
        -- did the reference publish *anything* for this meeting? A meeting the
        -- feed does not cover is absent data, not a 100% disagreement, so the
        -- distance below must be null rather than a spurious 50%.
        max(case when j.ecbwatch_probability is not null then 1 else 0 end)
            over (partition by j.meeting_date)               as has_ecbwatch
    from joined j
)

select
    meeting_date,
    scenario_rate,
    local_probability,
    ecbwatch_probability,
    diff_pp,
    case
        when has_ecbwatch = 1 then
            0.5 * 100 * sum(
                abs(coalesce(local_probability, 0) - coalesce(ecbwatch_probability, 0))
            ) over (partition by meeting_date)
    end                                                      as total_variation_pp,
    (local_probability is not null
     and ecbwatch_probability is not null)                   as matched,
    ecbwatch_current_rate,
    source_last_updated,
    source_version,
    source_status,
    source_data_sources,
    ecbwatch_known_at
from scored
order by meeting_date, scenario_rate
