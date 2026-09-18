#!/usr/bin/env python3
"""Load the roadmap proposal into the local Plane instance.

Reads research/plane-roadmap-proposal.json and materialises it in Plane as a
project, work-item states, labels, modules and work items.

Community Edition constraints (verified against the v1.4.2 backend):
  * Initiatives do not exist — there is no `initiative` route in either the
    public API or the app API in this release. The proposal's initiative layer
    is therefore encoded as one label per initiative (`init: <name>`), applied
    to every work item belonging to that initiative's modules, so the grouping
    stays filterable.
  * Milestones do not exist either. Each module's milestones are written into
    the module description as a checklist so no planning detail is lost.
Upgrading to the commercial edition would let both become first-class objects.

The script is idempotent: states, labels, modules and work items are matched by
name and reused rather than duplicated, so it can be re-run safely.

Usage:
    python seed_roadmap.py                 # seed (creates whatever is missing)
    python seed_roadmap.py --dry-run       # report what would change
    python seed_roadmap.py --verify        # print current roadmap status
    python seed_roadmap.py --fresh-project # delete the onboarding demo project
                                           # first, then create a clean one
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
PROPOSAL = PROJECT_ROOT / "research" / "plane-roadmap-proposal.json"
CREDENTIALS = HERE / ".credentials.local"

# Representative state per Plane state group, used to place a work item when the
# proposal only names a group.
GROUP_STATE = {
    "backlog": "Backlog",
    "unstarted": "Todo",
    "started": "In Progress",
    "completed": "Done",
    "cancelled": "Cancelled",
}

MODULE_STATUS = {
    "planned": "planned",
    "in-progress": "in-progress",
    "completed": "completed",
    "paused": "paused",
    "cancelled": "cancelled",
}

# Plane creates a native Triage state (group "triage") for every new project but
# hides it from the public states API. Attempting to create a state with that
# name collides with the hidden row, and Plane's handler turns the resulting
# duplicate-key error into a bare HTTP 500 instead of a 409. We therefore treat
# these names as already present.
NATIVE_HIDDEN_STATES = {"Triage"}


# --------------------------------------------------------------------------- #
# credentials
# --------------------------------------------------------------------------- #
def load_credentials() -> dict[str, str]:
    if not CREDENTIALS.exists():
        sys.exit(f"error: {CREDENTIALS} not found — see infra/plane/README.md")
    creds: dict[str, str] = {}
    for line in CREDENTIALS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        creds[key.strip()] = value.strip()
    for required in ("WEB_URL", "API_KEY", "WORKSPACE_SLUG"):
        if not creds.get(required):
            sys.exit(f"error: {required} missing from {CREDENTIALS}")
    return creds


# --------------------------------------------------------------------------- #
# markdown -> html (the descriptions use only bold, inline code and bullets)
# --------------------------------------------------------------------------- #
def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    return out


def md_to_html(md: str) -> str:
    parts: list[str] = []
    in_list = False
    for raw in (md or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue
        bullet = re.match(r"^\s*[-*]\s+(.*)$", line)
        if bullet:
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline(bullet.group(1))}</li>")
            continue
        if in_list:
            parts.append("</ul>")
            in_list = False
        parts.append(f"<p>{_inline(line)}</p>")
    if in_list:
        parts.append("</ul>")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# API client
# --------------------------------------------------------------------------- #
class Plane:
    def __init__(self, base_url: str, token: str, slug: str, dry_run: bool = False):
        self.base = base_url.rstrip("/")
        self.slug = slug
        self.dry = dry_run
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": token, "Content-Type": "application/json"})
        self.writes = 0

    # -- low level ---------------------------------------------------------- #
    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base}/api/v1/workspaces/{self.slug}{path}"
        for attempt in range(5):
            resp = self.session.request(method, url, timeout=60, **kwargs)
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                print(f"    rate limited; sleeping {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            return resp
        return resp

    def get_all(self, path: str) -> list[dict]:
        items: list[dict] = []
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else None
            resp = self._request("GET", path, params=params)
            if resp.status_code != 200:
                sys.exit(f"GET {path} failed: {resp.status_code} {resp.text[:300]}")
            data = resp.json()
            if isinstance(data, list):
                return data
            items.extend(data.get("results", []))
            if not data.get("next_page_results"):
                return items
            cursor = data.get("next_cursor")

    def write(self, method: str, path: str, payload: dict) -> dict:
        """POST/PATCH with idle throttling; returns the decoded body."""
        if self.dry:
            return {"__dry_run__": True}
        # Keep well clear of API_KEY_RATE_LIMIT (300/min on this instance).
        time.sleep(0.05)
        resp = self._request(method, path, json=payload)
        self.writes += 1
        if resp.status_code not in (200, 201, 204):
            raise RuntimeError(
                f"{method} {path} -> {resp.status_code}\n{resp.text[:600]}\npayload={json.dumps(payload)[:400]}"
            )
        return resp.json() if resp.content else {}

    def delete(self, path: str) -> None:
        if self.dry:
            return
        resp = self._request("DELETE", path)
        if resp.status_code not in (200, 204):
            raise RuntimeError(f"DELETE {path} -> {resp.status_code} {resp.text[:300]}")
        self.writes += 1


# --------------------------------------------------------------------------- #
# seeding
# --------------------------------------------------------------------------- #
def find_or_create_project(api: Plane, proposal: dict, fresh: bool) -> str:
    inst = proposal["instance"]
    projects = api.get_all("/projects/")
    identifier = inst["project_identifier"]

    for proj in projects:
        if proj.get("identifier") == identifier:
            print(f"  project {identifier} already exists ({proj['id']})")
            return proj["id"]

    # Plane's onboarding seeds a demo project ("Plane Demo Project" description).
    if fresh:
        for proj in projects:
            if "Demo Project" in (proj.get("description") or ""):
                print(f"  removing onboarding demo project {proj['identifier']} ({proj['id']})")
                api.delete(f"/projects/{proj['id']}/")

    payload = {
        "name": inst["project_name"],
        "identifier": identifier,
        "description": proposal.get("project_summary", ""),
        "project_lead": None,
    }
    created = api.write("POST", "/projects/", payload)
    pid = created.get("id", "<dry-run>")
    print(f"  created project {identifier} ({pid})")
    return pid


def ensure_project_features(api: Plane, pid: str) -> None:
    """Enable the project views the roadmap depends on.

    A project created through the API starts with modules, cycles and views
    disabled (only Plane's onboarding demo project has them on), and module
    creation fails with "Modules are not enabled for this project" until
    module_view is set.
    """
    wanted = {
        "module_view": True,
        "cycle_view": True,
        "issue_views_view": True,
        "page_view": True,
    }
    current = api.write("PATCH", f"/projects/{pid}/", wanted)
    if not api.dry:
        off = [k for k in wanted if not current.get(k)]
        print(f"    views enabled: {', '.join(sorted(wanted))}" + (f" (FAILED: {off})" if off else ""))


def ensure_states(api: Plane, pid: str, wanted: list[dict]) -> dict[str, str]:
    existing = {s["name"]: s["id"] for s in api.get_all(f"/projects/{pid}/states/")}
    for state in wanted:
        name = state["name"]
        if name in existing:
            continue
        if name in NATIVE_HIDDEN_STATES:
            print(f"    = state {name} provided natively by Plane (hidden from the API)")
            continue
        try:
            body = api.write(
                "POST",
                f"/projects/{pid}/states/",
                {"name": name, "color": state["color"], "group": state["group"]},
            )
        except RuntimeError as exc:
            # Guard against any other hidden/racing row: re-read before failing.
            refreshed = {s["name"]: s["id"] for s in api.get_all(f"/projects/{pid}/states/")}
            if name in refreshed:
                existing[name] = refreshed[name]
                continue
            raise RuntimeError(f"could not create state {name!r}: {exc}") from exc
        existing[name] = body.get("id", "<dry-run>")
        print(f"    + state {name} ({state['group']})")
    return existing


def ensure_labels(api: Plane, pid: str, wanted: list[dict]) -> dict[str, str]:
    existing = {l["name"]: l["id"] for l in api.get_all(f"/projects/{pid}/labels/")}
    for label in wanted:
        name = label["name"]
        if name in existing:
            continue
        body = api.write(
            "POST",
            f"/projects/{pid}/labels/",
            {"name": name, "color": label["color"]},
        )
        existing[name] = body.get("id", "<dry-run>")
    print(f"    labels available: {len(existing)}")
    return existing


def module_description(module: dict, why: str) -> str:
    """Module description, with milestone detail folded in (CE has no milestones)."""
    desc = module.get("description", "")
    milestones = module.get("milestones") or []
    if not milestones:
        return desc
    lines = [desc, "", "Milestones (checkpoints for this module):"]
    for ms in milestones:
        target = ms.get("target_date") or "no date"
        lines.append(f"- {ms['name']} — {target}")
    if why:
        lines += ["", f"Why it matters: {why}"]
    return "\n".join(lines)


def ensure_modules(api: Plane, pid: str, proposal: dict) -> dict[str, str]:
    reasons = {i["name"]: i.get("description", "") for i in proposal["initiatives"]}
    existing = {m["name"]: m["id"] for m in api.get_all(f"/projects/{pid}/modules/")}
    for module in proposal["modules"]:
        name = module["name"]
        if name in existing:
            continue
        body = api.write(
            "POST",
            f"/projects/{pid}/modules/",
            {
                "name": name,
                "description": module_description(module, ""),
                "start_date": module.get("start_date"),
                "target_date": module.get("target_date"),
                "status": MODULE_STATUS.get(module.get("state", "planned"), "planned"),
            },
        )
        existing[name] = body.get("id", "<dry-run>")
    print(f"    modules available: {len(existing)}")
    return existing


def ensure_work_items(
    api: Plane,
    pid: str,
    proposal: dict,
    states: dict[str, str],
    labels: dict[str, str],
    modules: dict[str, str],
) -> None:
    # Map module -> initiative so work items can carry the initiative label.
    module_to_initiative = {m["name"]: m["initiative"] for m in proposal["modules"]}
    initiatives = {i["name"] for i in proposal["initiatives"]}

    # One label per initiative, standing in for the missing Initiatives feature.
    for name in sorted(initiatives):
        label_name = f"init: {name}"
        if label_name not in labels:
            body = api.write(
                "POST",
                f"/projects/{pid}/labels/",
                {"name": label_name, "color": "#1D4ED8"},
            )
            labels[label_name] = body.get("id", "<dry-run>")
    print(f"    initiative labels: {len(initiatives)}")

    existing = {i["name"]: i for i in api.get_all(f"/projects/{pid}/issues/")}
    print(f"    existing work items: {len(existing)}")

    # Current module membership, so only genuinely-missing links are posted.
    membership: dict[str, str] = {}
    for module_name, module_id in modules.items():
        if not module_id or module_id == "<dry-run>":
            continue
        for it in api.get_all(f"/projects/{pid}/modules/{module_id}/module-issues/"):
            membership[it["id"]] = module_name

    created = repaired = correct = 0
    to_link: dict[str, list[str]] = {}

    for item in proposal["work_items"]:
        name = item["name"]
        # NOTE: the API field is `state` (a UUID FK), not `state_id`. Sending
        # `state_id` is silently ignored by the serializer, leaving the item in
        # the project's default state.
        target_state = states[GROUP_STATE[item["state_group"]]]
        label_ids = [labels[n] for n in item.get("labels", []) if n in labels]
        initiative = module_to_initiative.get(item["module"])
        if initiative and f"init: {initiative}" in labels:
            label_ids.append(labels[f"init: {initiative}"])

        current = existing.get(name)
        if current is None:
            body = api.write(
                "POST",
                f"/projects/{pid}/issues/",
                {
                    "name": name,
                    "description_html": md_to_html(item.get("description_markdown", "")),
                    "priority": item.get("priority", "none"),
                    "state": target_state,
                    "labels": label_ids,
                },
            )
            created += 1
            iid = body.get("id")
        else:
            # Converge an already-present item onto the proposal, so re-running
            # after a fix repairs earlier partial writes instead of skipping them.
            iid = current["id"]
            changes: dict = {}
            if current.get("state") != target_state:
                changes["state"] = target_state
            if set(current.get("labels") or []) != set(label_ids):
                changes["labels"] = label_ids
            if changes:
                api.write("PATCH", f"/projects/{pid}/issues/{iid}/", changes)
                repaired += 1
            else:
                correct += 1

        if iid and iid != "<dry-run>" and membership.get(iid) != item["module"]:
            to_link.setdefault(item["module"], []).append(iid)

    print(f"    created {created}, repaired {repaired}, already correct {correct}")

    # Attach work items to their modules in one call per module.
    linked = 0
    for module_name, issue_ids in to_link.items():
        module_id = modules.get(module_name)
        if not module_id or not issue_ids:
            continue
        api.write(
            "POST",
            f"/projects/{pid}/modules/{module_id}/module-issues/",
            {"issues": issue_ids},
        )
        linked += len(issue_ids)
    print(f"    linked {linked} work items into {len(to_link)} modules")


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #
def verify(api: Plane, pid: str, proposal: dict) -> None:
    """Print a roadmap status report: totals, priorities and per-module progress."""
    states = api.get_all(f"/projects/{pid}/states/")
    labels = api.get_all(f"/projects/{pid}/labels/")
    modules = api.get_all(f"/projects/{pid}/modules/")
    issues = api.get_all(f"/projects/{pid}/issues/")

    print("\n=== Plane roadmap status ===")
    print(f"  states:     {len(states):3}  (proposal: {len(proposal['states'])}, incl. Plane's hidden native Triage)")
    print(f"  labels:     {len(labels):3}  (proposal: {len(proposal['labels'])} + initiative labels)")
    print(f"  modules:    {len(modules):3}  (proposal: {len(proposal['modules'])})")
    print(f"  work items: {len(issues):3}  (proposal: {len(proposal['work_items'])})")

    by_priority: dict[str, int] = {}
    state_by_id = {s["id"]: s for s in states}
    for issue in issues:
        pri = issue.get("priority") or "none"
        by_priority[pri] = by_priority.get(pri, 0) + 1
    order = ["urgent", "high", "medium", "low", "none"]
    print("  by priority: " + ", ".join(f"{k}={by_priority.get(k, 0)}" for k in order if by_priority.get(k)))

    done_groups = {"completed", "cancelled"}
    today = time.strftime("%Y-%m-%d")
    total_done = 0
    overdue: list[tuple[str, str]] = []

    print("\n  module progress (done/total):")
    for module in sorted(modules, key=lambda m: (m.get("start_date") or "9999", m["name"])):
        items = api.get_all(f"/projects/{pid}/modules/{module['id']}/module-issues/")
        done = sum(
            1
            for it in items
            if state_by_id.get(it.get("state") or (it.get("state_id")), {}).get("group") in done_groups
        )
        total_done += done
        total = len(items)
        pct = f"{done * 100 // total:3d}%" if total else "  – "
        bar = ("#" * (done * 10 // total)).ljust(10, ".") if total else "." * 10
        target = module.get("target_date")
        flag = ""
        if target and target < today and module.get("status") != "completed":
            flag = "  <-- PAST TARGET"
            overdue.append((module["name"], target))
        print(
            f"    {module.get('status','?'):12} {module.get('start_date') or '—'} → {target or '—':10} "
            f"[{bar}] {pct} {done:2}/{total:<2}  {module['name']}{flag}"
        )

    if issues:
        print(f"\n  overall: {total_done}/{len(issues)} work items in a closed state ({total_done * 100 // len(issues)}%)")
    if overdue:
        print(f"  {len(overdue)} module(s) past target date without completion: "
              + ", ".join(f"{n} ({d})" for n, d in overdue))


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--verify", action="store_true", help="print current roadmap status and exit")
    ap.add_argument(
        "--fresh-project",
        action="store_true",
        help="delete Plane's onboarding demo project before seeding",
    )
    args = ap.parse_args()

    creds = load_credentials()
    proposal = json.loads(PROPOSAL.read_text())
    api = Plane(creds["WEB_URL"], creds["API_KEY"], creds["WORKSPACE_SLUG"], dry_run=args.dry_run)

    if args.verify:
        pid = next(
            p["id"]
            for p in api.get_all("/projects/")
            if p.get("identifier") == proposal["instance"]["project_identifier"]
        )
        verify(api, pid, proposal)
        return

    print(f"Seeding Plane from {PROPOSAL.relative_to(PROJECT_ROOT)}")
    print(f"  workspace: {creds['WORKSPACE_SLUG']}  ({creds['WEB_URL']})")
    if args.dry_run:
        print("  DRY RUN — no writes will be made")

    print("\n[1/5] project")
    pid = find_or_create_project(api, proposal, args.fresh_project)
    ensure_project_features(api, pid)

    print("\n[2/5] states")
    states = ensure_states(api, pid, proposal["states"])
    if args.dry_run:
        for s in proposal["states"]:
            states.setdefault(s["name"], "<dry-run>")

    print("\n[3/5] labels")
    labels = ensure_labels(api, pid, proposal["labels"])

    print("\n[4/5] modules")
    modules = ensure_modules(api, pid, proposal)

    print("\n[5/5] work items")
    if args.dry_run:
        print(f"    would create {len(proposal['work_items'])} work items")
    else:
        ensure_work_items(api, pid, proposal, states, labels, modules)

    print(f"\nwrites issued: {api.writes}")
    if not args.dry_run:
        verify(api, pid, proposal)


if __name__ == "__main__":
    main()
