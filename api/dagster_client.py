"""Dagster GraphQL client — launch runs and read their status/events.

The UI triggers work through the API (spec §10 owner-only router), and the API
triggers Dagster. Dagster is the only writer here: the API never runs ingest or
dbt itself, it just asks for a run and reports what happened.

Only the webserver is spoken to (``DAGSTER_URL``), never the daemon: the daemon
picks the queued run up and executes it.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

DAGSTER_URL: str = os.getenv("DAGSTER_URL", "http://dagster-webserver:3000").rstrip("/")
REPO_LOCATION: str = os.getenv("DAGSTER_REPOSITORY_LOCATION", "orchestration.definitions")
REPO_NAME: str = os.getenv("DAGSTER_REPOSITORY_NAME", "__repository__")

#: Run statuses that mean "still going".
ACTIVE_STATUSES = {
    "QUEUED", "NOT_STARTED", "STARTING", "STARTED", "MANAGED", "CANCELING",
}

_LAUNCH = """
mutation Launch($params: ExecutionParams!) {
  launchRun(executionParams: $params) {
    __typename
    ... on LaunchRunSuccess { run { runId status } }
    ... on InvalidStepError { invalidStepKey }
    ... on InvalidOutputError { stepKey invalidOutputName }
    ... on RunConfigValidationInvalid { errors { message reason } }
    ... on PipelineNotFoundError { message }
    ... on RunConflict { message }
    ... on InvalidSubsetError { message }
    ... on UnauthorizedError { message }
    ... on PythonError { message stack }
  }
}
"""

_STATUS = """
query Status($runId: ID!) {
  runOrError(runId: $runId) {
    __typename
    ... on Run {
      runId
      jobName
      status
      startTime
      endTime
      updateTime
      tags { key value }
      stats { ... on RunStatsSnapshot { stepsSucceeded stepsFailed } }
      eventConnection(limit: 400) {
        events {
          __typename
          ... on ExecutionStepStartEvent { stepKey message timestamp }
          ... on ExecutionStepSuccessEvent { stepKey message timestamp }
          ... on ExecutionStepFailureEvent { stepKey message timestamp error { message } }
          ... on RunFailureEvent { message timestamp error { message } }
          ... on EngineEvent { message timestamp }
          ... on LogMessageEvent { message timestamp level }
          ... on AssetMaterializationPlannedEvent { message timestamp }
          ... on MaterializationEvent { stepKey message timestamp }
        }
      }
    }
    ... on RunNotFoundError { message }
    ... on PythonError { message }
  }
}
"""


class DagsterError(RuntimeError):
    """A GraphQL call failed or returned a Dagster-side error."""


def _post(query: str, variables: dict, timeout: float = 30.0) -> dict:
    try:
        resp = requests.post(
            f"{DAGSTER_URL}/graphql",
            json={"query": query, "variables": variables},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise DagsterError(
            f"cannot reach the Dagster webserver at {DAGSTER_URL}: {exc}"
        ) from exc
    if resp.status_code >= 400:
        raise DagsterError(f"Dagster GraphQL HTTP {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    if body.get("errors"):
        msgs = "; ".join(e.get("message", "?") for e in body["errors"])
        raise DagsterError(f"Dagster GraphQL error: {msgs}")
    return body.get("data") or {}


def launch_run(job_name: str, run_config: dict | None = None,
               tags: dict[str, str] | None = None) -> dict:
    """Queue a run of ``job_name`` and return {run_id, status, job_name}.

    ``run_config`` is plain run config (e.g. ``{"ops": {"ingest_one_series":
    {"config": {"series_id": "DGS10"}}}}``).
    """
    params: dict[str, Any] = {
        "selector": {
            "repositoryLocationName": REPO_LOCATION,
            "repositoryName": REPO_NAME,
            "jobName": job_name,
        },
        "executionMetadata": {"tags": [{"key": k, "value": v}
                                       for k, v in (tags or {}).items()]},
    }
    if run_config:
        params["runConfigData"] = run_config
    data = _post(_LAUNCH, {"params": params})
    result = data.get("launchRun") or {}
    kind = result.get("__typename")
    if kind != "LaunchRunSuccess":
        detail = (
            result.get("message")
            or result.get("invalidStepKey")
            or result.get("errors")
            or result
        )
        raise DagsterError(f"Dagster refused the run ({kind}): {detail}")
    run = result.get("run") or {}
    return {"run_id": run.get("runId"), "status": run.get("status"),
            "job_name": job_name}


def run_status(run_id: str, include_events: bool = True) -> dict:
    """Current status of a run, optionally with its event log."""
    query = _STATUS if include_events else """
        query Status($runId: ID!) {
          runOrError(runId: $runId) {
            __typename
            ... on Run { runId jobName status startTime endTime updateTime
                         stats { ... on RunStatsSnapshot { stepsSucceeded stepsFailed } } }
            ... on RunNotFoundError { message }
            ... on PythonError { message }
          }
        }
    """
    data = _post(query, {"runId": run_id})
    run = data.get("runOrError") or {}
    if run.get("__typename") != "Run":
        raise DagsterError(f"run {run_id}: {run.get('message', 'not found')}")

    status = run.get("status")
    stats = run.get("stats") or {}
    out = {
        "run_id": run.get("runId"),
        "job_name": run.get("jobName"),
        "status": status,
        "is_running": status in ACTIVE_STATUSES,
        "ok": status == "SUCCESS",
        "start_time": _iso(run.get("startTime")),
        "end_time": _iso(run.get("endTime")),
        "update_time": _iso(run.get("updateTime")),
        "steps_succeeded": stats.get("stepsSucceeded"),
        "steps_failed": stats.get("stepsFailed"),
        "dagster_url": f"{DAGSTER_URL}/runs/{run_id}",
        "events": [],
    }
    if include_events:
        events = ((run.get("eventConnection") or {}).get("events")) or []
        out["events"] = [_event(e) for e in events]
    return out


#: Above this, an epoch value is milliseconds rather than seconds.
#: (Dagster's GraphQL `startTime` is epoch *milliseconds* in older releases and
#: epoch *seconds* in 1.13 — sniffing the magnitude works for both: 1e11 seconds
#: is year 5138, 1e11 millis is 1973.)
_EPOCH_MS_THRESHOLD = 1e11


def _iso(value) -> str | None:
    """Render a Dagster epoch timestamp as UTC ISO for the API/UI."""
    if value in (None, ""):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if num > _EPOCH_MS_THRESHOLD:
        num /= 1000.0
    try:
        return datetime.fromtimestamp(num, tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return str(value)


def _event(e: dict) -> dict:
    """Flatten one Dagster event into {type, step, message, level, timestamp}."""
    kind = (e.get("__typename") or "").replace("Event", "")
    message = e.get("message") or ""
    error = e.get("error") or {}
    if error.get("message"):
        message = f"{message} — {error['message']}" if message else error["message"]
    return {
        "type": kind,
        "step": e.get("stepKey"),
        "message": " ".join(str(message).split())[:400],
        "level": e.get("level"),
        "timestamp": _iso(e.get("timestamp")),
    }


def health() -> dict:
    """Cheap connectivity probe for the UI's status badge."""
    try:
        data = _post(
            "query { version }",
            {},
            timeout=5.0,
        )
        return {"reachable": True, "url": DAGSTER_URL, "version": data.get("version")}
    except DagsterError as exc:
        return {"reachable": False, "url": DAGSTER_URL, "error": str(exc)}


def list_runs(limit: int = 20, job_names: list[str] | None = None) -> list[dict]:
    """Most recent runs, optionally filtered to a set of jobs.

    This Dagster's ``RunsFilter`` has no ``jobNames`` field (only a single
    ``pipelineName``), so the job filter is applied here rather than in GraphQL:
    over-fetch, then keep the newest ``limit`` runs of the wanted jobs.
    """
    query = """
    query Runs($limit: Int!) {
      runsOrError(limit: $limit) {
        __typename
        ... on Runs {
          results { runId jobName status startTime endTime }
        }
        ... on PythonError { message }
      }
    }
    """
    want = set(job_names) if job_names else None
    fetch = max(int(limit), 30) if want else int(limit)
    data = _post(query, {"limit": fetch})
    res = data.get("runsOrError") or {}
    if res.get("__typename") != "Runs":
        raise DagsterError(f"cannot list runs: {res.get('message', res)}")
    rows = res.get("results", [])
    if want:
        rows = [r for r in rows if r.get("jobName") in want]
    return [
        {
            "run_id": r.get("runId"),
            "job_name": r.get("jobName"),
            "status": r.get("status"),
            "is_running": r.get("status") in ACTIVE_STATUSES,
            "start_time": _iso(r.get("startTime")),
            "end_time": _iso(r.get("endTime")),
            "dagster_url": f"{DAGSTER_URL}/runs/{r.get('runId')}",
        }
        for r in rows[: int(limit)]
    ]


def terminate_run(run_id: str) -> dict:
    query = """
    mutation Terminate($runId: String!) {
      terminateRun(runId: $runId, terminatePolicy: MARK_AS_CANCELED_IMMEDIATELY) {
        __typename
        ... on TerminateRunSuccess { run { runId status } }
        ... on TerminateRunFailure { message }
        ... on RunNotFoundError { message }
        ... on PythonError { message }
      }
    }
    """
    data = _post(query, {"runId": run_id})
    res = data.get("terminateRun") or {}
    if res.get("__typename") != "TerminateRunSuccess":
        raise DagsterError(f"cannot terminate {run_id}: {res.get('message', res)}")
    return {"run_id": run_id, "status": (res.get("run") or {}).get("status")}
