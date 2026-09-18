---
title: OLTP vs OLAP
type: concept
status: seedling
tags: [oltp, olap, databases, workloads]
created: 2026-09-18
updated: 2026-09-18
aliases: [OLTP, OLAP, Transactional vs Analytical Workloads]
---

# OLTP vs OLAP
OLTP systems serve many small transactional reads and writes over current state, while OLAP systems serve fewer, larger analytical queries over history.

## Why it matters
- Workload shape drives schema, indexing, and storage choices, and one engine rarely serves both well.
- Row-oriented storage suits point lookups; column-oriented storage suits aggregate scans.
- Mixing the two puts long analytical scans in the path of user-facing latency.
- Normalised schemas protect write integrity; dimensional or wide schemas make reads cheap.

## How it works
The split shows up in access pattern more than in product names.

| | OLTP | OLAP |
|---|---|---|
| Question | what is true now | what happened over time |
| Query | point lookup, small transaction | aggregate scan, group by |
| Rows touched | few | many |
| Storage | row-oriented | column-oriented |
| Schema | normalised | star or wide |

A single Postgres instance can host both workloads if they are separated by schema and scheduling, but the optimisations pull in opposite directions.

## In this platform
Ingestion writes append-only raw payloads into a Postgres warehouse, while dbt rebuilds staging and marts with full-refresh models and the FastAPI and Metabase layers issue aggregate reads. Both sides run on the same Postgres, so the separation appears as schema boundaries (raw, staging, marts) and as Dagster's daily schedule rather than as two engines. The bitemporal fact grain is an analytical structure, not a transactional one, and it would not be a sensible target for high-volume point writes.

## Related
- [[Bitemporal Data]]
- [[Semantic Layer]]
- [[Data Quality]]
- [[Change Data Capture]]

## Further reading
- [OLAP vs OLTP (IBM)](https://www.ibm.com/think/topics/olap-vs-oltp)
- [The Data Warehouse Toolkit (Kimball and Ross)](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/books/)
