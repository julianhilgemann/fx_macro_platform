#!/usr/bin/env python3
"""Build a Metabase "Series Explorer" collection.

Creates a new root collection ("folder") in Metabase and, inside it, one
time-series line chart per active series in the warehouse:

    marts.dim_series            -> series catalog (id, title, unit, category, ...)
    marts.fct_macro_observation -> observations (obs_date, value, is_latest)

Cards are grouped into a sub-collection per `category` so the 79 series stay
browsable. Re-running archives the previous "FX Macro — Series Explorer"
collection first, so it is safe to run repeatedly.

Requires MB_API_KEY (Metabase API key) and a reachable Metabase at
http://127.0.0.1:3001 (the local docker-compose `metabase` service).
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("MB_BASE", "http://127.0.0.1:3001")
KEY = os.environ.get("MB_API_KEY", "").strip()

TOP_COLLECTION_NAME = "FX Macro — Series Explorer"

SERIES_SQL = """
SELECT series_id, title, unit, frequency, category, description
FROM marts.dim_series
WHERE active
ORDER BY category, series_id
"""


def req(method, path, payload=None):
    url = BASE + path
    data = None
    headers = {"x-api-key": KEY}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"  ! HTTP {e.code} {method} {path}: {body[:400]}", file=sys.stderr)
        return None


def find_warehouse_db():
    """Return the id of the `fx_macro` Postgres database, or exit."""
    resp = req("GET", "/api/database")
    if not resp or "data" not in resp:
        sys.exit("Could not list databases")
    for db in resp["data"]:
        if db.get("engine") == "postgres" and db.get("name") == "fx_macro":
            return db["id"]
    sys.exit("`fx_macro` Postgres database not found in Metabase")


def fetch_series(db_id):
    """Return ordered list of series dicts (series_id, title, unit, category, ...)."""
    payload = {
        "database": db_id,
        "type": "native",
        "native": {"query": SERIES_SQL},
    }
    resp = req("POST", "/api/dataset", payload)
    if not resp or "data" not in resp:
        sys.exit(f"Could not query series catalog: {resp}")
    data = resp["data"]
    cols = [c["name"] for c in data["cols"]]
    series = []
    for row in data["rows"]:
        series.append(dict(zip(cols, row)))
    return series


def find_collection(name, parent_id=None):
    resp = req("GET", "/api/collection")
    if not resp:
        return None
    for c in resp:
        if c.get("name") == name and c.get("parent_id") == parent_id and not c.get("archived"):
            return c
    return None


def archive_collection(cid):
    """Trash (archive) an existing collection so re-runs don't duplicate.

    Metabase requires archiving first; hard-delete (`DELETE`) only works on an
    already-archived collection. Archiving the parent also trashes its children.
    """
    r = req("PUT", f"/api/collection/{cid}", {"archived": True})
    print(f"  trashed old collection {cid}" if r is not None else f"  ! trash failed for {cid}")


def create_collection(name, parent_id=None, description=None):
    payload = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    if description:
        payload["description"] = description
    r = req("POST", "/api/collection", payload)
    if r and r.get("id"):
        return r
    print(f"  ! create collection failed for {name!r}: {json.dumps(r)[:300]}", file=sys.stderr)
    return None


def card_name(title, series_id, seen):
    name = title or series_id
    if name in seen:
        name = f"{name} ({series_id})"
    seen.add(name)
    return name


def main():
    if not KEY:
        sys.exit("MB_API_KEY is not set")

    db_id = find_warehouse_db()
    print(f"warehouse db id: {db_id}")

    series = fetch_series(db_id)
    if not series:
        sys.exit("No active series found in marts.dim_series")
    print(f"found {len(series)} active series")

    # Idempotency: archive a previous run of this builder.
    old = find_collection(TOP_COLLECTION_NAME, parent_id=None)
    if old:
        archive_collection(old["id"])

    top = create_collection(TOP_COLLECTION_NAME, description="One time-series line chart per series in the FX macro warehouse.")
    if not top:
        sys.exit("Failed to create top-level collection")
    print(f"top collection: {TOP_COLLECTION_NAME!r} (id {top['id']})")

    # Group into category sub-collections (stable ordering).
    categories = {}
    for s in series:
        cat = (s.get("category") or "other").strip()
        categories.setdefault(cat, []).append(s)

    seen_names = set()
    total_cards = 0
    for cat, items in categories.items():
        label = cat.replace("_", " ").replace("-", " ").title()
        sub = create_collection(label, parent_id=top["id"])
        if not sub:
            print(f"  ! skipping category {cat!r}: could not create sub-collection", file=sys.stderr)
            continue
        for idx, s in enumerate(items):
            sid = s["series_id"]
            title = s.get("title") or sid
            unit = s.get("unit")
            freq = s.get("frequency")
            desc = s.get("description") or ""
            # Postgres quoted-identifier escaping for the value alias.
            alias = title.replace('"', '""')
            sql = (
                'SELECT f.obs_date AS "Date", f.value AS "{alias}"\n'
                "FROM marts.fct_macro_observation f\n"
                "WHERE f.is_latest = TRUE\n"
                "  AND f.series_id = '{sid}'\n"
                "ORDER BY f.obs_date"
            ).format(alias=alias, sid=sid)

            name = card_name(title, sid, seen_names)
            card_desc = f"{desc}\n\nseries_id: {sid} • frequency: {freq or '?'} • category: {cat}".strip()
            payload = {
                "name": name,
                "display": "line",
                "description": card_desc,
                "visualization_settings": {
                    "graph.dimensions": ["Date"],
                    "graph.metrics": [title],
                    "graph.x_axis.axis_enabled": True,
                    "graph.y_axis.axis_enabled": True,
                    "graph.x_axis.title_text": "Date",
                    "graph.y_axis.title_text": unit or "",
                    "graph.show_values": False,
                    "graph.x_axis.labels_enabled": True,
                    "graph.y_axis.labels_enabled": True,
                },
                "dataset_query": {
                    "type": "native",
                    "native": {"query": sql, "template-tags": {}},
                    "database": db_id,
                },
                "collection_id": sub["id"],
                "collection_position": idx + 1,
            }
            r = req("POST", "/api/card", payload)
            if r and r.get("id"):
                total_cards += 1
            else:
                print(f"  ! card create failed for {sid}: {json.dumps(r)[:200]}", file=sys.stderr)

        print(f"  [{label}] {len(items)} series")

    print(f"\nDONE: {total_cards} cards in {BASE}/collection/{top['id']}")


if __name__ == "__main__":
    main()
