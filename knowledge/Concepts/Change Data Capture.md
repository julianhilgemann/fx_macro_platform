---
title: Change Data Capture
type: concept
status: seedling
tags: [cdc, ingestion, incremental, data-pipelines]
created: 2026-09-18
updated: 2026-09-18
aliases: [CDC, Incremental Ingestion]
---

# Change Data Capture
Change data capture (CDC) records row-level inserts, updates, and deletes from a source as a stream of change events, so downstream systems apply only what actually changed.

## Why it matters
- It avoids re-reading and reprocessing data that did not change.
- It preserves the order and timing of changes, which repeated full snapshots lose.
- It keeps derived tables close to the source instead of rebuilding them wholesale.
- It turns "what changed since last time?" into an explicit, auditable signal.

## How it works
Two common forms. Log-based CDC tails the database write-ahead log (Debezium on Postgres logical replication) and captures every committed change, including deletes. Query-based CDC polls a timestamp or version column, which is simpler but misses hard deletes and can miss intermediate states.

```sql
-- query-based CDC: only rows past the last watermark
select *
from raw.source_fetch
where fetched_at > :last_watermark
order by fetched_at;
```

Events carry an operation type and are idempotent when keyed by a stable key plus a log position or checksum.

## In this platform
The raw landing zone is append-only and sha256-indexed, but the `payload_sha256` column is never used for change detection, so byte-identical fetches are not skipped. FRED revision history is not captured at all, and ECB and Bundesbank re-stamp the whole history on each fetch rather than inserting only on change. A real change-detection path keyed on `payload_sha256`, plus per-observation diffing, would be the smallest useful step toward CDC here.

## Related
- [[Idempotency]]
- [[Bitemporal Data]]
- [[Event-Driven Architecture]]
- [[Data Quality]]

## Further reading
- [Debezium Features](https://debezium.io/documentation/reference/stable/features.html)
- [Designing Data-Intensive Applications (Kleppmann), ch. 11](https://dataintensive.net/)
