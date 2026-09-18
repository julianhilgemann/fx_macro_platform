#!/usr/bin/env python3
"""Migrate the roadmap proposal to GitHub Issues, Labels and Milestones.

Reads research/plane-roadmap-proposal.json (produced for the Plane deployment)
and materialises it on GitHub:

  * labels      <- the 19 proposed labels + one per roadmap theme (initiative)
  * milestones  <- the 15 modules, with due_on = the module's target date
  * issues      <- the 82 work items, with description, acceptance criteria,
                   evidence, labels and milestone

Idempotent: existing labels, milestones and issues are matched by name/title and
reused, so re-running repairs rather than duplicates. Writes an issue map to
.issues-map.json for the Projects v2 step.

Usage:
    python migrate_roadmap.py --dry-run     # show what would change
    python migrate_roadmap.py               # perform the migration
    python migrate_roadmap.py --verify      # report current GitHub state
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
PROPOSAL = PROJECT_ROOT / "research" / "plane-roadmap-proposal.json"
TOKEN_FILE = HERE / ".token"
ISSUE_MAP = HERE / ".issues-map.json"

API = "https://api.github.com"

# GitHub secondary rate limits bite well below the hourly REST quota when
# creating content, so every write is paced.
WRITE_DELAY = 1.1


def load_token() -> str:
    import os

    if os.environ.get("GH_TOKEN"):
        return os.environ["GH_TOKEN"]
    if TOKEN_FILE.exists() and TOKEN_FILE.read_text().strip():
        return TOKEN_FILE.read_text().strip()
    sys.exit(
        f"error: no GitHub token.\n"
        f"  Save a fine-grained PAT (Issues: read/write, Projects: read/write) to\n"
        f"  {TOKEN_FILE}\n"
        f"  or export GH_TOKEN."
    )


def detect_repo() -> str:
    """owner/repo from the git remote, so this is not hardcoded."""
    try:
        url = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        sys.exit("error: could not read git remote 'origin'")
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("git@"):
        url = url.split(":", 1)[1]
    parts = url.rstrip("/").split("/")
    return f"{parts[-2]}/{parts[-1]}"


class GitHub:
    def __init__(self, repo: str, token: str, dry_run: bool = False):
        self.repo = repo
        self.dry = dry_run
        self.s = requests.Session()
        self.s.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self.writes = 0

    def _req(self, method: str, path: str, **kw) -> requests.Response:
        url = path if path.startswith("http") else f"{API}{path}"
        for attempt in range(5):
            r = self.s.request(method, url, timeout=60, **kw)
            if r.status_code in (403, 429) and "rate limit" in r.text.lower():
                wait = 60
                print(f"    rate limited; sleeping {wait}s", flush=True)
                time.sleep(wait)
                continue
            if r.status_code == 502:
                time.sleep(3)
                continue
            return r
        return r

    def get_all(self, path: str) -> list[dict]:
        """Fetch every page of a list endpoint (GitHub caps per_page at 100)."""
        out: list[dict] = []
        sep = "&" if "?" in path else "?"
        page = 1
        while True:
            r = self._req("GET", f"{API}{path}{sep}per_page=100&page={page}")
            if r.status_code != 200:
                sys.exit(f"GET {path} failed: {r.status_code} {r.text[:300]}")
            batch = r.json()
            if isinstance(batch, dict):
                return [batch]
            out.extend(batch)
            if len(batch) < 100:
                return out
            page += 1

    def write(self, method: str, path: str, payload: dict) -> dict:
        if self.dry:
            return {"__dry_run__": True}
        time.sleep(WRITE_DELAY)
        r = self._req(method, f"{API}{path}", json=payload)
        self.writes += 1
        if r.status_code not in (200, 201):
            raise RuntimeError(f"{method} {path} -> {r.status_code}\n{r.text[:500]}")
        return r.json()

    def graphql(self, query: str, variables: dict | None = None) -> tuple[dict, list]:
        """Returns (data, errors) rather than raising, so callers can report."""
        r = self._req(
            "POST",
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables or {}},
        )
        if not r.content:
            return {}, [{"message": f"HTTP {r.status_code}"}]
        body = r.json()
        return body.get("data") or {}, body.get("errors") or []


def preflight(gh: GitHub) -> bool:
    """Verify the token can actually do the migration, before writing anything.

    The most likely failure by far is a fine-grained token missing the Projects
    account permission — that only surfaces as a GraphQL permission error deep
    into the run, so it is checked up front and named explicitly.
    """
    ok = True
    print(f"Preflight for {gh.repo}")

    r = gh._req("GET", f"{API}/user")
    if r.status_code != 200:
        print(f"  FAIL  token rejected by GitHub ({r.status_code}: {r.text[:120]})")
        return False
    user = r.json()
    print(f"  ok    token valid — {user.get('login')} ({user.get('type', 'User').lower()})")

    scopes = r.headers.get("x-oauth-scopes")
    have: set[str] | None = None
    if scopes is not None:
        have = {s.strip() for s in scopes.split(",") if s.strip()}
        print(f"  ..    classic PAT scopes: {', '.join(sorted(have)) or '(none)'}")
        # 'project' is always required (Projects v2 access). 'repo'/'public_repo'
        # is only required for WRITING to the repository, and only 'repo' is
        # needed for a private one — so it is judged after we learn visibility.
        if "project" not in have:
            print("  FAIL  classic PAT is missing the 'project' scope")
            ok = False
    else:
        print("  ..    fine-grained token (no scope header) — checking access directly")

    r = gh._req("GET", f"{API}/repos/{gh.repo}")
    if r.status_code != 200:
        print(f"  FAIL  cannot read {gh.repo} ({r.status_code}) — check repository access")
        return False
    repo_info = r.json()
    perms = repo_info.get("permissions") or {}
    granted = ", ".join(k for k, v in perms.items() if v) or "read"
    print(f"  ok    repository readable — permissions: {granted}")

    if have is not None and not ({"repo", "public_repo"} & have):
        if repo_info.get("private"):
            print("  FAIL  private repository requires the 'repo' scope")
            ok = False
        else:
            print("  warn  no 'repo'/'public_repo' scope: reads work on a public repo,")
            print("        but creating or editing issues/labels/milestones will fail")
    if not perms.get("push"):
        print("  warn  no push permission reported; Issues write must be granted separately")

    # Projects v2 — the permission most often forgotten, and the one that has
    # actually bitten here. Probe project CONTENT (nodes), not totalCount:
    # totalCount is readable without the Projects permission, so a
    # totalCount-only check passes while every real project call fails.
    data, errors = gh.graphql("query{viewer{projectsV2(first:1){totalCount nodes{id}}}}")
    if errors:
        msg = errors[0].get("message", "")
        print(f"  FAIL  Projects v2 not usable: {msg[:120]}")
        print("        For a USER-owned project GitHub requires a classic PAT with")
        print("        the 'project' scope (and 'repo' if items come from private")
        print("        repos). Fine-grained tokens only cover ORGANIZATION projects.")
        print("        Create one at https://github.com/settings/tokens/new")
        ok = False
    else:
        conn = (data.get("viewer") or {}).get("projectsV2") or {}
        print(f"  ok    Projects v2 readable ({conn.get('totalCount')} existing project(s))")

    r = gh._req("GET", f"{API}/rate_limit")
    if r.status_code == 200:
        core = (r.json().get("resources") or {}).get("core") or {}
        print(f"  ..    REST quota remaining: {core.get('remaining')}/{core.get('limit')}")

    print("  ->    " + ("ready to migrate" if ok else "NOT ready — fix the failures above"))
    return ok


# --------------------------------------------------------------------------- #
def ensure_labels(gh: GitHub, proposal: dict) -> dict[str, str]:
    existing = {l["name"]: l["name"] for l in gh.get_all(f"/repos/{gh.repo}/labels")}
    wanted = [{"name": l["name"], "color": l["color"].lstrip("#"), "description": (l.get("description") or "")[:100]}
              for l in proposal["labels"]]
    # One label per roadmap theme, standing in for Plane's absent Initiatives.
    for init in proposal["initiatives"]:
        wanted.append(
            {
                "name": f"init: {init['name']}",
                "color": "1D4ED8",
                "description": (init.get("description") or "")[:100],
            }
        )

    created = 0
    for label in wanted:
        if label["name"] in existing:
            continue
        gh.write("POST", f"/repos/{gh.repo}/labels", label)
        existing[label["name"]] = label["name"]
        created += 1
    print(f"    labels: {created} created, {len(existing)} total")
    return existing


def ensure_milestones(gh: GitHub, proposal: dict) -> dict[str, int]:
    existing = {m["title"]: m["number"] for m in gh.get_all(f"/repos/{gh.repo}/milestones?state=all")}
    created = 0
    for module in proposal["modules"]:
        title = module["name"]
        if title in existing:
            continue
        payload: dict = {
            "title": title,
            "description": (module.get("description") or "")[:1000],
            "state": "closed" if module.get("state") == "completed" else "open",
        }
        # GitHub milestones accept a due date but no start date; the start date
        # lives on the Project's Start date field instead.
        if module.get("target_date"):
            payload["due_on"] = f"{module['target_date']}T00:00:00Z"
        body = gh.write("POST", f"/repos/{gh.repo}/milestones", payload)
        number = body.get("number")
        if number:
            existing[title] = number
        created += 1
    print(f"    milestones: {created} created, {len(existing)} total")
    return existing


def issue_body(item: dict, proposal: dict) -> str:
    module = next((m for m in proposal["modules"] if m["name"] == item["module"]), {})
    parts = [item.get("description_markdown", "").strip()]
    parts.append("\n\n---\n")
    parts.append(
        f"**Module:** {item['module']}  \n"
        f"**Initiative:** {module.get('initiative', '—')}  \n"
        f"**Priority:** {item.get('priority', 'none')}  \n"
        f"**Estimate:** {item.get('estimate_points', '—')} points  \n"
        f"**Evidence:** `{item.get('evidence', '—')}`"
    )
    parts.append(
        "\n\n<sub>Imported from `research/plane-roadmap-proposal.json` "
        "(migrated from Plane CE, which lacks Initiatives and Milestones).</sub>"
    )
    return "".join(parts)


def ensure_issues(
    gh: GitHub,
    proposal: dict,
    labels: dict[str, str],
    milestones: dict[str, int],
) -> dict[str, dict]:
    existing = {i["title"]: i for i in gh.get_all(f"/repos/{gh.repo}/issues?state=all")}
    module_to_initiative = {m["name"]: m["initiative"] for m in proposal["modules"]}

    created = repaired = correct = 0
    mapping: dict[str, dict] = {}

    for item in proposal["work_items"]:
        title = item["name"]
        label_names = [n for n in item.get("labels", []) if n in labels]
        initiative = module_to_initiative.get(item["module"])
        if initiative and f"init: {initiative}" in labels:
            label_names.append(f"init: {initiative}")

        milestone_number = milestones.get(item["module"])
        current = existing.get(title)

        if current is None:
            payload: dict = {"title": title, "body": issue_body(item, proposal), "labels": label_names}
            if milestone_number:
                payload["milestone"] = milestone_number
            # NOTE: the create-issue endpoint does not accept `state`, so already
            # finished work is created open and closed immediately below.
            body = gh.write("POST", f"/repos/{gh.repo}/issues", payload)
            number = body.get("number")
            if item["state_group"] == "completed":
                gh.write(
                    "PATCH",
                    f"/repos/{gh.repo}/issues/{number}",
                    {"state": "closed", "state_reason": "completed"},
                )
            created += 1
            mapping[title] = {"number": number, "node_id": body.get("node_id")}
            continue

        # Converge an existing issue onto the proposal.
        number = current["number"]
        mapping[title] = {"number": number, "node_id": current.get("node_id")}
        changes: dict = {}
        want_closed = item["state_group"] == "completed"
        if current.get("state") != ("closed" if want_closed else "open"):
            changes["state"] = "closed" if want_closed else "open"
            if want_closed:
                changes["state_reason"] = "completed"
        current_labels = {l["name"] for l in current.get("labels", [])}
        if current_labels != set(label_names):
            changes["labels"] = label_names
        if changes:
            gh.write("PATCH", f"/repos/{gh.repo}/issues/{number}", changes)
            repaired += 1
        else:
            correct += 1

    print(f"    issues: {created} created, {repaired} repaired, {correct} already correct")
    return mapping


def verify(gh: GitHub, proposal: dict) -> None:
    labels = gh.get_all(f"/repos/{gh.repo}/labels")
    milestones = gh.get_all(f"/repos/{gh.repo}/milestones?state=all")
    issues = [i for i in gh.get_all(f"/repos/{gh.repo}/issues?state=all") if "pull_request" not in i]

    print(f"\n=== GitHub roadmap state ({gh.repo}) ===")
    print(f"  labels:     {len(labels):3}  (proposal: {len(proposal['labels'])} + {len(proposal['initiatives'])} themes)")
    print(f"  milestones: {len(milestones):3}  (proposal modules: {len(proposal['modules'])})")
    print(f"  issues:     {len(issues):3}  (proposal: {len(proposal['work_items'])})")

    closed = sum(1 for i in issues if i["state"] == "closed")
    print(f"  closed:     {closed}/{len(issues)}")

    # Roadmap themes are carried as `init: <theme>` labels.
    themes: dict[str, int] = {}
    for issue in issues:
        for label in issue.get("labels", []):
            if label["name"].startswith("init: "):
                key = label["name"][6:]
                themes[key] = themes.get(key, 0) + 1
    if themes:
        print("  by theme: " + ", ".join(f"{k}={v}" for k, v in sorted(themes.items(), key=lambda x: -x[1])))

    print("\n  milestones (progress):")
    for m in sorted(milestones, key=lambda x: (x.get("due_on") or "9999")):
        total = m["open_issues"] + m["closed_issues"]
        pct = f"{m['closed_issues'] * 100 // total:3d}%" if total else "  – "
        due = (m.get("due_on") or "—")[:10]
        print(f"    {due}  {pct}  {m['closed_issues']:2}/{total:<2}  {m['title']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--preflight", action="store_true", help="check the token and permissions, then exit")
    ap.add_argument("--repo", help="owner/repo (default: from git remote)")
    args = ap.parse_args()

    token = load_token()
    repo = args.repo or detect_repo()
    proposal = json.loads(PROPOSAL.read_text())
    gh = GitHub(repo, token, dry_run=args.dry_run)

    if args.preflight:
        sys.exit(0 if preflight(gh) else 1)

    if args.verify:
        verify(gh, proposal)
        return

    print(f"Migrating {PROPOSAL.name} -> {repo}")
    if args.dry_run:
        print("  DRY RUN — no writes")

    print("\n[1/3] labels")
    labels = ensure_labels(gh, proposal)
    if args.dry_run:
        for lbl in proposal["labels"]:
            labels.setdefault(lbl["name"], lbl["name"])

    print("\n[2/3] milestones (modules)")
    milestones = ensure_milestones(gh, proposal)

    print("\n[3/3] issues")
    mapping = ensure_issues(gh, proposal, labels, milestones)

    print(f"\nwrites issued: {gh.writes}")
    if not args.dry_run:
        ISSUE_MAP.write_text(json.dumps(mapping, indent=2))
        print(f"issue map written to {ISSUE_MAP.name} ({len(mapping)} entries)")
        verify(gh, proposal)


if __name__ == "__main__":
    main()
