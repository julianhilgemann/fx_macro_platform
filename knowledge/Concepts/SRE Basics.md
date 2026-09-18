---
title: SRE Basics
type: concept
status: seedling
tags: [reliability, operations, sre]
created: 2026-09-18
updated: 2026-09-18
aliases: [SRE, Site Reliability Engineering]
---

# SRE Basics

Site reliability engineering applies software engineering to operations, replacing vague reliability hopes with measured targets and an explicit error budget.

## Why it matters

- Service level indicators and objectives turn "reliable enough" into a number that can be monitored and argued about with evidence.
- The error budget makes the shipping versus stability tradeoff explicit instead of political.
- Toil reduction targets the manual, repetitive work that quietly consumes operator time and causes mistakes.
- Blameless incident reviews fix systems and process rather than people, which is the only way to get honest reporting.

## How it works

Pick a few indicators that reflect user experience, set an objective over a window, and derive the budget from it. When the budget is exhausted, reliability work takes priority over new features.

```yaml
sli: pipeline_freshness
definition: share of daily runs where marts are refreshed before 08:00 local
slo: 99% over 30 days
error_budget: 1% (about 7 hours per month)
alert: burn rate > 2x over 6 hours -> page
```

## In this platform

No SLOs are defined for FX Macro Platform, and there is no alerting yet. The reliability signals that do exist are Dagster run status for the daily pipeline and Elementary data-quality, freshness, and anomaly reports; the rest is manual checking with `docker compose logs` and `docker stats`. `docs/observability-plan.md` is a proposal and nothing in it is applied. A first SLO around pipeline freshness would be a natural starting point, since the daily schedule makes the target easy to state.

## Related

- [[Observability]]
- [[Observability Stack]]
- [[Data Quality]]

## Further reading

- [Site Reliability Engineering, Google](https://sre.google/sre-book/table-of-contents/)
- [The Site Reliability Workbook](https://sre.google/workbook/table-of-contents/)
- [Implementing SLOs](https://sre.google/workbook/implementing-slos/)
