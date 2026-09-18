#!/usr/bin/env python3
"""Build the Projects v2 board and roadmap for the migrated roadmap.

Runs after migrate_roadmap.py, and is idempotent — it reuses an existing project
of the same title, existing fields, and existing items, so it can be re-run.

It creates:
  * a Project v2 owned by the repo owner
  * a Status single-select (Backlog / Todo / In Progress / In Review / Blocked /
    Done) driving the kanban columns
  * Priority, Initiative (single-select), Estimate (number) and Start/Target
    date (date) fields
  * one project item per migrated issue, with those fields populated from
    state_group, priority, module and module dates

Views (Board / Roadmap) are created when the API supports it; GitHub has not
always exposed view creation over GraphQL, so the script reports clearly and
prints the one-click manual fallback when it cannot.

Usage:
    python build_project.py --dry-run
    python build_project.py
    python build_project.py --verify
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
STATE_FILE = HERE / ".project.json"

GRAPHQL = "https://api.github.com/graphql"
PROJECT_TITLE = "FX Macro Platform — Roadmap"

STATUS_OPTIONS = [
    ("Backlog", "GRAY"),
    ("Todo", "BLUE"),
    ("In Progress", "YELLOW"),
    ("In Review", "PURPLE"),
    ("Blocked", "RED"),
    ("Done", "GREEN"),
]
STATE_GROUP_TO_STATUS = {
    "backlog": "Backlog",
    "unstarted": "Todo",
    "started": "In Progress",
    "completed": "Done",
    "cancelled": "Done",
}
PRIORITY_OPTIONS = [("Urgent", "RED"), ("High", "ORANGE"), ("Medium", "YELLOW"), ("Low", "GRAY")]
INITIATIVE_COLORS = ["BLUE", "GREEN", "PURPLE", "ORANGE", "PINK", "GRAY"]

BATCH = 12


def load_token() -> str:
    import os

    if os.environ.get("GH_TOKEN"):
        return os.environ["GH_TOKEN"]
    if TOKEN_FILE.exists() and TOKEN_FILE.read_text().strip():
        return TOKEN_FILE.read_text().strip()
    sys.exit(f"error: no GitHub token at {TOKEN_FILE} (or export GH_TOKEN)")


def detect_owner() -> str:
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
    return url.rstrip("/").split("/")[-2]


class Gh:
    def __init__(self, token: str, dry_run: bool = False):
        self.dry = dry_run
        self.s = requests.Session()
        self.s.headers.update(
            {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        )
        self.calls = 0

    def gql(self, query: str, variables: dict | None = None) -> dict:
        if self.dry:
            return {}
        for attempt in range(4):
            r = self.s.post(GRAPHQL, json={"query": query, "variables": variables or {}}, timeout=90)
            if r.status_code in (403, 429):
                time.sleep(20)
                continue
            body = r.json()
            if "errors" in body:
                msgs = [e.get("message", "") for e in body["errors"]]
                # A token without Projects permission fails on every project
                # call; the raw error gives no hint that a classic PAT is
                # required for user-owned projects.
                if any("not accessible" in m for m in msgs):
                    raise RuntimeError(PROJECTS_HELP)
                raise RuntimeError(f"GraphQL errors:\n{json.dumps(body['errors'], indent=1)[:800]}")
            self.calls += 1
            return body.get("data", {})
        raise RuntimeError(f"GraphQL request failed repeatedly: {r.status_code} {r.text[:300]}")


# --------------------------------------------------------------------------- #
def get_owner_id(gh: Gh, owner: str) -> str:
    """Resolve the owner's node id.

    The user and organization lookups must be separate requests: combining them
    into one document makes GraphQL validate `organization.id`, which requires
    the `read:org` scope, so a token holding only `project` fails the whole
    query even though it only needs the user branch.
    """
    data = gh.gql("query($login:String!){ user(login:$login){ id } }", {"login": owner})
    node = data.get("user") or {}
    if node.get("id"):
        return node["id"]

    data = gh.gql("query($login:String!){ organization(login:$login){ id } }", {"login": owner})
    node = data.get("organization") or {}
    if not node.get("id"):
        sys.exit(f"error: could not resolve owner '{owner}' as a user or organization")
    return node["id"]


def find_project(gh: Gh, owner: str, title: str) -> dict | None:
    data = gh.gql(
        """
        query($login:String!,$cursor:String){
          user(login:$login){
            projectsV2(first:50, after:$cursor){
              pageInfo{hasNextPage endCursor}
              nodes{ id number title }
            }
          }
        }
        """,
        {"login": owner},
    )
    user = data.get("user") or {}
    for node in (user.get("projectsV2") or {}).get("nodes", []):
        if node["title"] == title:
            return node
    return None


def project_by_number(gh: Gh, owner: str, number: int) -> dict:
    """Resolve an existing project by its number, so a hand-made board can be
    brought up to parity instead of only the one this script creates."""
    data = gh.gql(
        "query($login:String!,$number:Int!){user(login:$login){projectV2(number:$number){id number title}}}",
        {"login": owner, "number": number},
    )
    node = (data.get("user") or {}).get("projectV2")
    if not node:
        sys.exit(f"error: no project #{number} for {owner}")
    return node


def create_project(gh: Gh, owner_id: str, title: str) -> dict:
    data = gh.gql(
        """
        mutation($ownerId:ID!,$title:String!){
          createProjectV2(input:{ownerId:$ownerId,title:$title}){
            projectV2{ id number title }
          }
        }
        """,
        {"ownerId": owner_id, "title": title},
    )
    return data["createProjectV2"]["projectV2"]


def list_fields(gh: Gh, project_id: str) -> dict[str, dict]:
    data = gh.gql(
        """
        query($id:ID!){
          node(id:$id){
            ... on ProjectV2{
              fields(first:50){
                nodes{
                  __typename
                  ... on ProjectV2FieldCommon{ id name dataType }
                  ... on ProjectV2SingleSelectField{ id name options{ id name } }
                }
              }
            }
          }
        }
        """,
        {"id": project_id},
    )
    out: dict[str, dict] = {}
    for f in ((data.get("node") or {}).get("fields") or {}).get("nodes", []):
        if f and f.get("name"):
            out[f["name"]] = f
    return out


def ensure_single_select(gh: Gh, project_id: str, fields: dict, name: str, options: list[tuple[str, str]]) -> dict:
    """Create a single-select field, or reconcile an existing one's options."""
    if gh.dry:
        # Dry runs make no network calls, so synthesise a shaped field rather
        # than indexing into the empty response gh.gql() returns.
        field = {
            "id": f"<dry-run:{name}>",
            "name": name,
            "dataType": "SINGLE_SELECT",
            "options": [{"id": f"<dry-run:{name}:{n}>", "name": n} for n, _ in options],
        }
        fields[name] = field
        return field

    wanted = [{"name": n, "color": c, "description": ""} for n, c in options]
    existing = fields.get(name)
    if existing is None:
        data = gh.gql(
            """
            mutation($projectId:ID!,$name:String!,$options:[ProjectV2SingleSelectFieldOptionInput!]!){
              createProjectV2Field(input:{
                projectId:$projectId, dataType:SINGLE_SELECT, name:$name, singleSelectOptions:$options
              }){ projectV2Field{ ... on ProjectV2SingleSelectField{ id name options{ id name } } } }
            }
            """,
            {"projectId": project_id, "name": name, "options": wanted},
        )
        field = data["createProjectV2Field"]["projectV2Field"]
        fields[name] = field
        return field

    have = {o["name"] for o in existing.get("options", [])}
    if have == {n for n, _ in options}:
        return existing

    # Preserve ids of options we keep, so already-set values survive.
    merged = []
    by_name = {o["name"]: o for o in existing.get("options", [])}
    for n, c in options:
        if n in by_name:
            merged.append({"id": by_name[n]["id"], "name": n, "color": c, "description": ""})
        else:
            merged.append({"name": n, "color": c, "description": ""})
    data = gh.gql(
        """
        mutation($fieldId:ID!,$options:[ProjectV2SingleSelectFieldOptionInput!]!){
          updateProjectV2Field(input:{fieldId:$fieldId, singleSelectOptions:$options}){
            projectV2Field{ ... on ProjectV2SingleSelectField{ id name options{ id name } } }
          }
        }
        """,
        {"fieldId": existing["id"], "options": merged},
    )
    field = data["updateProjectV2Field"]["projectV2Field"]
    fields[name] = field
    return field


def ensure_simple_field(gh: Gh, project_id: str, fields: dict, name: str, data_type: str) -> dict:
    if name in fields:
        return fields[name]
    if gh.dry:
        field = {"id": f"<dry-run:{name}>", "name": name, "dataType": data_type}
        fields[name] = field
        return field
    data = gh.gql(
        """
        mutation($projectId:ID!,$name:String!,$dataType:ProjectV2CustomFieldType!){
          createProjectV2Field(input:{projectId:$projectId, dataType:$dataType, name:$name}){
            projectV2Field{ ... on ProjectV2FieldCommon{ id name dataType } }
          }
        }
        """,
        {"projectId": project_id, "name": name, "dataType": data_type},
    )
    field = data["createProjectV2Field"]["projectV2Field"]
    fields[name] = field
    return field


def existing_items(gh: Gh, project_id: str) -> dict[str, str]:
    """content node id -> project item id."""
    out: dict[str, str] = {}
    cursor = None
    while True:
        data = gh.gql(
            """
            query($id:ID!,$cursor:String){
              node(id:$id){
                ... on ProjectV2{
                  items(first:100, after:$cursor){
                    pageInfo{hasNextPage endCursor}
                    nodes{ id content{ ... on Issue{ id } } }
                  }
                }
              }
            }
            """,
            {"id": project_id, "cursor": cursor},
        )
        items = ((data.get("node") or {}).get("items")) or {}
        for it in items.get("nodes", []):
            content = it.get("content") or {}
            if content.get("id"):
                out[content["id"]] = it["id"]
        page = items.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return out
        cursor = page["endCursor"]


def populated_fields(gh: Gh, project_id: str) -> dict[str, set[str]]:
    """item id -> names of fields that already carry a value.

    Lets value population be additive: a re-run fills blanks but never overwrites
    a human's manual triage with the proposal's original values.
    """
    out: dict[str, set[str]] = {}
    cursor = None
    while True:
        data = gh.gql(
            """
            query($id:ID!,$c:String){
              node(id:$id){ ... on ProjectV2{
                items(first:100, after:$c){
                  pageInfo{hasNextPage endCursor}
                  nodes{
                    id
                    fieldValues(first:30){nodes{
                      ... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2FieldCommon{name}}}
                      ... on ProjectV2ItemFieldDateValue{date field{... on ProjectV2FieldCommon{name}}}
                      ... on ProjectV2ItemFieldNumberValue{number field{... on ProjectV2FieldCommon{name}}}
                    }}
                  }
                }
              }}
            }
            """,
            {"id": project_id, "c": cursor},
        )
        items = ((data.get("node") or {}).get("items")) or {}
        for it in items.get("nodes", []):
            names: set[str] = set()
            for fv in (it.get("fieldValues") or {}).get("nodes", []):
                if fv.get("name") is None and fv.get("date") is None and fv.get("number") is None:
                    continue
                fname = (fv.get("field") or {}).get("name")
                if fname:
                    names.add(fname)
            out[it["id"]] = names
        page = items.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return out
        cursor = page["endCursor"]


def add_items(gh: Gh, project_id: str, content_ids: list[str]) -> dict[str, str]:
    """Add issues to the project; returns content id -> item id."""
    if gh.dry:
        return {cid: f"<dry-run-item:{i}>" for i, cid in enumerate(content_ids)}
    added: dict[str, str] = {}
    for i in range(0, len(content_ids), BATCH):
        chunk = content_ids[i : i + BATCH]
        parts = [
            f'a{k}: addProjectV2ItemById(input:{{projectId:"{project_id}", contentId:"{cid}"}})'
            f"{{ item{{ id }} }}"
            for k, cid in enumerate(chunk)
        ]
        data = gh.gql("mutation{" + " ".join(parts) + "}")
        for k, cid in enumerate(chunk):
            # With an alias the response key is the alias and its value IS the
            # payload — {a0: {item: {id}}} — NOT {a0: {addProjectV2ItemById: ...}}.
            # Nesting the field name under the alias silently yielded no ids.
            node = (data.get(f"a{k}") or {}).get("item") or {}
            if node.get("id"):
                added[cid] = node["id"]
        print(f"    added {min(i + BATCH, len(content_ids))}/{len(content_ids)} items", flush=True)
    return added


def _gql_value(value: dict) -> str:
    """Render a ProjectV2FieldValue in GraphQL input syntax.

    GraphQL input-object keys are bare names, so json.dumps() is wrong here: it
    quotes the keys and the parser rejects the document with
    'Expected NAME, actual: STRING'. String values are still JSON-encoded, which
    gives correct escaping.
    """
    parts = []
    for key, val in value.items():
        if isinstance(val, bool):
            rendered = "true" if val else "false"
        elif isinstance(val, str):
            rendered = json.dumps(val)
        else:
            rendered = str(val)
        parts.append(f"{key}: {rendered}")
    return "{" + ", ".join(parts) + "}"


def set_values(gh: Gh, project_id: str, updates: list[tuple[str, str, dict]]) -> None:
    """updates: (item_id, field_id, value-dict) — batched into aliased mutations."""
    for i in range(0, len(updates), BATCH):
        chunk = updates[i : i + BATCH]
        parts = []
        for k, (item_id, field_id, value) in enumerate(chunk):
            parts.append(
                f'b{k}: updateProjectV2ItemFieldValue(input:{{projectId:"{project_id}", '
                f'itemId:"{item_id}", fieldId:"{field_id}", value:{_gql_value(value)}}})'
                f"{{ projectV2Item{{ id }} }}"
            )
        gh.gql("mutation{" + " ".join(parts) + "}")
        print(f"    set values {min(i + BATCH, len(updates))}/{len(updates)}", flush=True)


def list_views(gh: Gh, project_id: str) -> list[dict]:
    data = gh.gql(
        """
        query($id:ID!){
          node(id:$id){ ... on ProjectV2{ views(first:50){ nodes{ id name layout } } } }
        }
        """,
        {"id": project_id},
    )
    return ((data.get("node") or {}).get("views") or {}).get("nodes", []) or []


def try_views(gh: Gh, project_id: str) -> bool:
    """Ensure a board-layout and a roadmap-layout view exist.

    Idempotent in two ways: same-named duplicates are removed (an earlier
    revision created views unconditionally on every run), and a wanted view is
    considered satisfied by ANY view of that layout — so a hand-made board named
    "Kanban" is respected rather than duplicated with a new "Board".
    """
    wanted = (("Board", "BOARD_LAYOUT"), ("Roadmap", "ROADMAP_LAYOUT"))
    views = list_views(gh, project_id)

    by_name: dict[str, list[dict]] = {}
    for view in views:
        by_name.setdefault(view["name"], []).append(view)
    for name, group in by_name.items():
        for extra in group[1:]:
            gh.gql(
                "mutation($id:ID!){deleteProjectV2View(input:{viewId:$id}){projectV2View{id}}}",
                {"id": extra["id"]},
            )
            print(f"    removed duplicate '{name}' view")

    have_layouts = {v["layout"] for v in views}
    ok = True
    for name, layout in wanted:
        if layout in have_layouts:
            print(f"    {layout.replace('_LAYOUT','').lower()} view already present — kept")
            continue
        try:
            gh.gql(
                """
                mutation($projectId:ID!,$name:String!,$layout:ProjectV2ViewLayout!){
                  createProjectV2View(input:{projectId:$projectId, name:$name, layout:$layout}){
                    projectV2View{ id name }
                  }
                }
                """,
                {"projectId": project_id, "name": name, "layout": layout},
            )
            print(f"    created '{name}' ({layout})")
        except Exception as exc:  # noqa: BLE001 - API availability varies
            print(f"    could not create '{name}' view automatically ({str(exc)[:90]}...)")
            ok = False
    return ok


# --------------------------------------------------------------------------- #
PROJECTS_HELP = (
    "error: this token cannot access Projects v2.\n"
    "  GitHub requires a CLASSIC PAT with the 'project' scope for USER-owned\n"
    "  projects ('repo' too if project items come from private repositories):\n"
    "      https://github.com/settings/tokens/new\n"
    "  Fine-grained PATs only cover ORGANIZATION-owned projects — the GraphQL\n"
    "  API returns 'Resource not accessible by personal access token' for them,\n"
    "  and no REST endpoint can create a user-owned project either.\n"
    "  Save the token to infra/github/.token, then re-run.\n"
    "\n"
    "  Alternatively, skip the board: the roadmap is already usable without it,\n"
    "  because every work item is filed under a milestone (with a target date)\n"
    "  and carries its theme as an 'init: <theme>' label. See\n"
    "  https://github.com/julianhilgemann/fx_macro_platform/milestones"
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--owner", help="project owner (default: git remote owner)")
    ap.add_argument(
        "--project-number",
        type=int,
        help="populate an existing project by number instead of creating/finding one by title",
    )
    ap.add_argument(
        "--force-values",
        action="store_true",
        help="overwrite field values that are already set (default: only fill blanks)",
    )
    args = ap.parse_args()

    token = load_token()
    owner = args.owner or detect_owner()
    proposal = json.loads(PROPOSAL.read_text())
    gh = Gh(token, dry_run=args.dry_run)

    if not ISSUE_MAP.exists():
        sys.exit(f"error: {ISSUE_MAP.name} not found — run migrate_roadmap.py first")
    issue_map = json.loads(ISSUE_MAP.read_text())
    print(f"Project owner: {owner}   issues mapped: {len(issue_map)}")

    if args.dry_run:
        project = None
    elif args.project_number is not None:
        project = project_by_number(gh, owner, args.project_number)
    else:
        project = find_project(gh, owner, PROJECT_TITLE)

    if args.verify:
        # Read-only: never create a project just to report on it.
        if not project:
            print(f"\nno project titled {PROJECT_TITLE!r} for {owner} yet")
            return
        fields = list_fields(gh, project["id"])
        items = existing_items(gh, project["id"])
        print(f"\n=== project #{project['number']} — {project['title']} ===")
        print(f"  fields: {', '.join(sorted(fields))}")
        print(f"  items:  {len(items)}")
        for name, f in sorted(fields.items()):
            opts = f.get("options")
            if opts:
                print(f"    {name}: " + ", ".join(o["name"] for o in opts))
        return

    if project:
        print(f"  reusing project #{project['number']} ({project['title']})")
    elif args.dry_run:
        print("  DRY RUN — would create project")
        project = {"id": "<dry-run>", "number": 0}
    else:
        project = create_project(gh, get_owner_id(gh, owner), PROJECT_TITLE)
        print(f"  created project #{project['number']} ({project['title']})")
    project_id = project["id"]

    print("\n[1/4] fields")
    fields = list_fields(gh, project_id) if not args.dry_run else {}
    status = ensure_single_select(gh, project_id, fields, "Status", STATUS_OPTIONS)
    priority = ensure_single_select(gh, project_id, fields, "Priority", PRIORITY_OPTIONS)
    initiative = ensure_single_select(
        gh,
        project_id,
        fields,
        "Initiative",
        [(i["name"], INITIATIVE_COLORS[k % len(INITIATIVE_COLORS)]) for k, i in enumerate(proposal["initiatives"])],
    )
    estimate = ensure_simple_field(gh, project_id, fields, "Estimate", "NUMBER")
    start_field = ensure_simple_field(gh, project_id, fields, "Start date", "DATE")
    target_field = ensure_simple_field(gh, project_id, fields, "Target date", "DATE")
    for f in (status, priority, initiative, estimate, start_field, target_field):
        print(f"    {f.get('name')} ({f.get('dataType') or 'SINGLE_SELECT'})")

    def option_id(field: dict, name: str) -> str | None:
        for o in field.get("options", []):
            if o["name"] == name:
                return o["id"]
        return None

    print("\n[2/4] items")
    content_ids = [v["node_id"] for v in issue_map.values() if v.get("node_id")]
    present = existing_items(gh, project_id) if not args.dry_run else {}
    missing = [c for c in content_ids if c not in present]
    if args.dry_run:
        print(f"    would add {len(missing or content_ids)} items")
        item_by_content = {}
    else:
        item_by_content = dict(present)
        if missing:
            item_by_content.update(add_items(gh, project_id, missing))
        print(f"    {len(item_by_content)} items on the board")

    print("\n[3/4] field values")
    modules = {m["name"]: m for m in proposal["modules"]}
    module_to_initiative = {m["name"]: m["initiative"] for m in proposal["modules"]}
    # Additive by default: fill blanks, never overwrite anything already set, so
    # re-running cannot clobber manual triage. --force-values overrides.
    already = populated_fields(gh, project_id) if not args.dry_run else {}
    updates: list[tuple[str, str, dict]] = []
    skipped_kept = 0
    for item in proposal["work_items"]:
        entry = issue_map.get(item["name"])
        if not entry:
            continue
        item_id = item_by_content.get(entry.get("node_id", ""))
        if not item_id and not args.dry_run:
            continue
        item_id = item_id or "<dry-run>"

        def add(field: dict, value: dict) -> None:
            nonlocal skipped_kept
            if not args.force_values and field["name"] in already.get(item_id, set()):
                skipped_kept += 1
                return
            updates.append((item_id, field["id"], value))

        sid = option_id(status, STATE_GROUP_TO_STATUS[item["state_group"]])
        if sid:
            add(status, {"singleSelectOptionId": sid})
        pid_opt = option_id(priority, (item.get("priority") or "none").capitalize())
        if pid_opt:
            add(priority, {"singleSelectOptionId": pid_opt})
        init_name = module_to_initiative.get(item["module"])
        iid = option_id(initiative, init_name) if init_name else None
        if iid:
            add(initiative, {"singleSelectOptionId": iid})
        if item.get("estimate_points"):
            add(estimate, {"number": float(item["estimate_points"])})
        module = modules.get(item["module"], {})
        if module.get("start_date"):
            add(start_field, {"date": module["start_date"]})
        if module.get("target_date"):
            add(target_field, {"date": module["target_date"]})

    print(f"    {len(updates)} values to set across {len(proposal['work_items'])} items")
    if skipped_kept:
        print(f"    {skipped_kept} existing values left untouched (use --force-values to overwrite)")
    if not args.dry_run:
        set_values(gh, project_id, updates)

    print("\n[4/4] views")
    if args.dry_run:
        print("    would create Board and Roadmap views")
    elif try_views(gh, project_id):
        print("    board and roadmap views present")
    else:
        print(
            "    Create them in the UI (10 seconds): open the project, 'New view',\n"
            "      - Board layout, group by Status\n"
            "      - Roadmap layout, date fields Start date / Target date"
        )

    if not args.dry_run:
        STATE_FILE.write_text(
            json.dumps({"owner": owner, "number": project["number"], "id": project_id}, indent=2)
        )
    print(f"\ngraphql calls: {gh.calls}")
    print(f"open: https://github.com/users/{owner}/projects/{project.get('number', '')}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        if "cannot access projects v2" in str(exc).lower():
            print(f"\n{exc}", file=sys.stderr)
            sys.exit(1)
        raise
