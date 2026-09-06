#!/usr/bin/env python3
"""Build sample Metabase dashboards for the FX macro warehouse.

Requires MB_API_KEY (Metabase API key) and a reachable Metabase at
http://127.0.0.1:3001 (the local docker-compose `metabase` service).
Reads the `fx_macro` database (id 2) and builds native-SQL line charts over
`marts.fct_macro_observation` + `marts.dim_series`.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("MB_BASE", "http://127.0.0.1:3001")
KEY = os.environ.get("MB_API_KEY", "").strip()

if not KEY:
    sys.exit("MB_API_KEY is not set")

DB_ID = 2  # "fx_macro" (postgres)


def req(method, path, payload=None, raw=False):
    url = BASE + path
    data = None
    headers = {"x-api-key": KEY}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            body = resp.read()
            if raw:
                return body, resp.status
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"  ! HTTP {e.code} {method} {path}: {body[:300]}", file=sys.stderr)
        return {"error": e.code, "body": body}


def set_row_limit(n=50000):
    # Native queries hit `unaggregated-query-row-limit` (max-results-bare-rows),
    # which must be <= `aggregated-query-row-limit` (max-results). Raise both.
    for setting in ("aggregated-query-row-limit", "unaggregated-query-row-limit"):
        r = req("PUT", f"/api/setting/{setting}", {"value": n})
        cur = req("GET", f"/api/setting/{setting}")
        print(f"{setting} -> {cur}")


def delete_card(cid):
    r = req("DELETE", f"/api/card/{cid}")
    print(f"deleted card {cid}" if not r.get("error") else f"card {cid} delete: {r.get('error')}")


# ---- card definitions ----
FACT = "marts.fct_macro_observation f"
DIM = "marts.dim_series d"
JOIN = f"JOIN {DIM} ON d.series_id = f.series_id"

CARDS = [
    dict(
        name="US Treasury 2Y vs 10Y",
        dashboard="treasury",
        y_title="Percent (%)",
        metrics=["US 2Y", "US 10Y"],
        sql=f"""
SELECT f.obs_date AS "Date",
       MAX(f.value) FILTER (WHERE d.series_id = 'DGS2')  AS "US 2Y",
       MAX(f.value) FILTER (WHERE d.series_id = 'DGS10') AS "US 10Y"
FROM {FACT} {JOIN}
WHERE f.is_latest = TRUE AND d.series_id IN ('DGS2','DGS10')
GROUP BY f.obs_date ORDER BY f.obs_date
""",
    ),
    dict(
        name="US 2s10s Spread",
        dashboard="treasury",
        y_title="Percentage points",
        metrics=["2s10s Spread"],
        sql=f"""
SELECT f.obs_date AS "Date",
       MAX(f.value) FILTER (WHERE d.series_id = 'DGS10')
       - MAX(f.value) FILTER (WHERE d.series_id = 'DGS2') AS "2s10s Spread"
FROM {FACT} {JOIN}
WHERE f.is_latest = TRUE AND d.series_id IN ('DGS10','DGS2')
GROUP BY f.obs_date ORDER BY f.obs_date
""",
    ),
    dict(
        name="US vs German 10Y Yield",
        dashboard="treasury",
        y_title="Percent (%)",
        metrics=["US 10Y", "German 10Y"],
        sql=f"""
SELECT f.obs_date AS "Date",
       MAX(f.value) FILTER (WHERE d.series_id = 'DGS10') AS "US 10Y",
       MAX(f.value) FILTER (WHERE d.series_id = 'DE10Y') AS "German 10Y"
FROM {FACT} {JOIN}
WHERE f.is_latest = TRUE AND d.series_id IN ('DGS10','DE10Y')
GROUP BY f.obs_date ORDER BY f.obs_date
""",
    ),
    dict(
        name="Fed Funds Target Range & Effective Rate",
        dashboard="policy",
        y_title="Percent (%)",
        metrics=["Target Upper", "Target Lower", "Effective Fed Funds"],
        sql=f"""
SELECT f.obs_date AS "Date",
       MAX(f.value) FILTER (WHERE d.series_id = 'DFEDTARU') AS "Target Upper",
       MAX(f.value) FILTER (WHERE d.series_id = 'DFEDTARL') AS "Target Lower",
       MAX(f.value) FILTER (WHERE d.series_id = 'FEDFUNDS') AS "Effective Fed Funds"
FROM {FACT} {JOIN}
WHERE f.is_latest = TRUE AND d.series_id IN ('DFEDTARU','DFEDTARL','FEDFUNDS')
GROUP BY f.obs_date ORDER BY f.obs_date
""",
    ),
    dict(
        name="ECB Deposit Facility Rate",
        dashboard="policy",
        y_title="Percent (%)",
        metrics=["ECB Deposit Rate"],
        sql=f"""
SELECT f.obs_date AS "Date", f.value AS "ECB Deposit Rate"
FROM {FACT} {JOIN}
WHERE f.is_latest = TRUE AND d.series_id = 'ECBDFR'
ORDER BY f.obs_date
""",
    ),
    dict(
        name="EUR/USD Spot",
        dashboard="fx",
        y_title="USD per EUR",
        metrics=["EUR/USD"],
        sql=f"""
SELECT f.obs_date AS "Date", f.value AS "EUR/USD"
FROM {FACT} {JOIN}
WHERE f.is_latest = TRUE AND d.series_id = 'DEXUSEU'
ORDER BY f.obs_date
""",
    ),
    dict(
        name="Broad USD Index",
        dashboard="fx",
        y_title="Index",
        metrics=["Broad USD Index"],
        sql=f"""
SELECT f.obs_date AS "Date", f.value AS "Broad USD Index"
FROM {FACT} {JOIN}
WHERE f.is_latest = TRUE AND d.series_id = 'DTWEXBGS'
ORDER BY f.obs_date
""",
    ),
    dict(
        name="VIX (CBOE Volatility Index)",
        dashboard="fx",
        y_title="Index",
        metrics=["VIX"],
        sql=f"""
SELECT f.obs_date AS "Date", f.value AS "VIX"
FROM {FACT} {JOIN}
WHERE f.is_latest = TRUE AND d.series_id = 'VIXCLS'
ORDER BY f.obs_date
""",
    ),
]

DASHBOARDS = [
    dict(key="treasury", name="FX Macro — Treasury & Yield Curve",
         description="US 2Y/10Y, 2s10s spread, and US vs German 10Y yields."),
    dict(key="policy", name="FX Macro — Policy Rates",
         description="Fed funds target range + effective rate, and ECB deposit rate."),
    dict(key="fx", name="FX Macro — FX & Risk",
         description="EUR/USD, broad USD index, and VIX."),
]


def make_card(card):
    payload = {
        "name": card["name"],
        "display": "line",
        "visualization_settings": {
            "graph.dimensions": ["Date"],
            "graph.metrics": card["metrics"],
            "graph.x_axis.axis_enabled": True,
            "graph.y_axis.axis_enabled": True,
            "graph.x_axis.title_text": "Date",
            "graph.y_axis.title_text": card["y_title"],
            "graph.show_values": False,
            "graph.x_axis.labels_enabled": True,
            "graph.y_axis.labels_enabled": True,
        },
        "dataset_query": {
            "type": "native",
            "native": {"query": card["sql"], "template-tags": {}},
            "database": DB_ID,
        },
    }
    r = req("POST", "/api/card", payload)
    if r.get("id"):
        print(f"  + card {r['id']}: {card['name']}")
        return r["id"]
    print(f"  ! card create failed: {json.dumps(r)[:300]}")
    return None


def save_dashboard(db, card_ids):
    """Create a dashboard with its cards in one shot via POST /api/dashboard/save.

    (v0.63 removed POST /api/dashboard/:id/cards; the modern denormalized
    save endpoint is what the frontend uses.)
    """
    layout = {
        "treasury": [(0, 0), (12, 0), (0, 6)],
        "policy": [(0, 0), (12, 0)],
        "fx": [(0, 0), (12, 0), (0, 6)],
    }[db["key"]]
    dashcards = [
        {"card": {"id": cid}, "size_x": 12, "size_y": 6, "row": row, "col": col}
        for cid, (row, col) in zip(card_ids, layout)
    ]
    payload = {
        "name": db["name"],
        "description": db["description"],
        "width": "fixed",
        "parameters": [],
        "tabs": [],
        "dashcards": dashcards,
    }
    r = req("POST", "/api/dashboard/save", payload)
    if r.get("id"):
        print(f"dashboard {r['id']}: {db['name']} ({len(card_ids)} cards)")
        return r["id"]
    print(f"! dashboard save failed for {db['name']}: {json.dumps(r)[:300]}")
    return None


def verify(cid, label):
    r = req("POST", f"/api/card/{cid}/query", {})
    data = (r or {}).get("data")
    if not data:
        print(f"  ! {label}: no data ({json.dumps(r)[:200]})")
        return
    rows = data.get("rows", [])
    cols = [c["name"] for c in data.get("cols", [])]
    print(f"  ok {label}: cols={cols} rows={len(rows)} last={rows[-1][0] if rows else '-'}")


def main():
    set_row_limit()

    card_ids = {}
    for card in CARDS:
        cid = make_card(card)
        if cid:
            card_ids[card["name"]] = cid

    dashboards = {}
    for db in DASHBOARDS:
        ids = [card_ids[c["name"]] for c in CARDS if c["dashboard"] == db["key"] and c["name"] in card_ids]
        did = save_dashboard(db, ids)
        if did:
            dashboards[db["key"]] = did

    print("\n=== verify cards ===")
    for name, cid in card_ids.items():
        verify(cid, name)

    print("\n=== dashboards ===")
    for key, did in dashboards.items():
        print(f"  {BASE}/dashboard/{did}")

    print("\nDONE")


if __name__ == "__main__":
    main()
