#!/usr/bin/env python
"""Run `dbt deps` in-container and serve the result as a self-contained HTML page.

Reads the same env knobs the other report services use:
  DBT_DEPS_REPORT_DIR       (default /reports)      where index.html + deps.log live
  DBT_DEPS_PORT             (default 8082)          host-facing port to serve on
  DBT_DEPS_REFRESH_SECONDS  (default 300)           re-run dbt deps + refresh page
  DBT_DEPS_PROJECT_DIR      (default /opt/app/dbt)  the dbt project root
"""

import html
import os
import re
import socket
import subprocess
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

REPORT_DIR = os.environ.get("DBT_DEPS_REPORT_DIR", "/reports")
PORT = int(os.environ.get("DBT_DEPS_PORT", "8082"))
REFRESH_SECONDS = int(os.environ.get("DBT_DEPS_REFRESH_SECONDS", "300"))
PROJECT_DIR = os.environ.get("DBT_DEPS_PROJECT_DIR", "/opt/app/dbt")

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def read_lock_packages() -> list[tuple[str, str]]:
    """Parse dbt/package-lock.yml into (name, version) pairs."""
    packages: list[tuple[str, str]] = []
    try:
        with open(os.path.join(PROJECT_DIR, "package-lock.yml"), "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        name = None
        for line in lines:
            m_name = re.match(r"\s*-\s*name:\s*(.*)", line)
            m_ver = re.match(r"\s*version:\s*(.*)", line)
            if m_name:
                name = m_name.group(1).strip()
            elif m_ver and name is not None:
                packages.append((name, m_ver.group(1).strip()))
                name = None
    except OSError:
        pass
    return packages


def _dbt_version() -> str:
    try:
        out = subprocess.run(
            ["dbt", "--version"], capture_output=True, text=True, timeout=30
        ).stdout or ""
        m = re.search(r"installed:\s*([0-9][0-9.]*)", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "unknown"


def run_deps() -> tuple[int, str, float, str]:
    started = time.time()
    dbt_version = _dbt_version()
    try:
        proc = subprocess.run(
            ["dbt", "deps", "--profiles-dir", "."],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        raw = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, raw, time.time() - started, dbt_version
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or "") + "\n[dbt-deps] TIMEOUT after 600s\n" + (exc.stderr or "")
        return 124, raw, time.time() - started, dbt_version
    except Exception as exc:  # noqa: BLE001
        return 127, f"[dbt-deps] failed to launch dbt: {exc!r}\n", time.time() - started, dbt_version


def build_html(rc: int, raw: str, elapsed: float, dbt_version: str,
               packages: list[tuple[str, str]]) -> str:
    ok = rc == 0
    status_text = "SUCCESS" if ok else f"FAILED (exit {rc})"
    status_class = "ok" if ok else "fail"

    rows = ""
    for name, version in packages:
        rows += (
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"<td class='mono'>{html.escape(version)}</td>"
            "</tr>"
        )
    if not rows:
        rows = "<tr><td colspan='2' class='muted'>No entries in package-lock.yml</td></tr>"

    tpl = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta http-equiv="refresh" content="__REFRESH__" />
<title>dbt deps — fx_macro</title>
<style>
  :root {
    --bg: #0f1115;
    --panel: #171a21;
    --panel-2: #1d212b;
    --text: #e6e8ee;
    --muted: #9aa1b0;
    --line: #2a2f3a;
    --green: #2fd57c;
    --green-soft: rgba(47, 213, 124, 0.14);
    --red: #ff5c6c;
    --red-soft: rgba(255, 92, 108, 0.14);
    --amber: #ffb224;
    --mono: "SFMono-Regular", ui-monospace, "JetBrains Mono", Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: radial-gradient(120% 90% at 50% -10%, #161a22 0%, var(--bg) 55%);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    min-height: 100vh;
    padding: 40px 20px 60px;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 960px; margin: 0 auto; }
  header { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 22px; }
  .kicker { font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--muted); }
  h1 { margin: 0; font-size: 30px; font-weight: 640; letter-spacing: -0.02em; }
  h1 .mono { color: var(--amber); }
  .badge {
    margin-left: auto;
    font-size: 12.5px; font-weight: 600; letter-spacing: 0.04em;
    padding: 7px 13px; border-radius: 999px; border: 1px solid;
  }
  .badge.ok { color: var(--green); background: var(--green-soft); border-color: rgba(47,213,124,0.35); }
  .badge.fail { color: var(--red); background: var(--red-soft); border-color: rgba(255,92,108,0.35); }

  .cards { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; margin-bottom: 20px; }
  .card {
    background: linear-gradient(160deg, var(--panel-2), var(--panel));
    border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px;
  }
  .card .k { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
  .card .v { margin-top: 6px; font-size: 15px; font-weight: 600; }
  .card .v.mono { font-family: var(--mono); font-weight: 500; }

  section { margin-bottom: 20px; }
  h2 {
    font-size: 13px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--muted); margin: 0 0 10px;
  }
  table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
  th, td { text-align: left; padding: 11px 16px; font-size: 13.5px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.06em; background: rgba(255,255,255,0.02); }
  tr:last-child td { border-bottom: 0; }
  .mono { font-family: var(--mono); }
  .muted { color: var(--muted); }

  pre {
    margin: 0; padding: 18px; overflow: auto;
    background: #0b0d11; border: 1px solid var(--line); border-radius: 14px;
    font-family: var(--mono); font-size: 12.5px; line-height: 1.6; color: #cdd3e0;
    max-height: 480px;
  }
  footer { margin-top: 26px; font-size: 12px; color: var(--muted); }
  @media (max-width: 720px) { .cards { grid-template-columns: repeat(2, minmax(0,1fr)); } }
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <div class="kicker">fx_macro · dependency install</div>
        <h1><span class="mono">dbt deps</span></h1>
      </div>
      <div class="badge __STATUS_CLASS__">__STATUS_TEXT__</div>
    </header>

    <div class="cards">
      <div class="card"><div class="k">dbt-core</div><div class="v mono">__DBT_VERSION__</div></div>
      <div class="card"><div class="k">host</div><div class="v mono">__HOST__</div></div>
      <div class="card"><div class="k">ran at (utc)</div><div class="v mono">__TS__</div></div>
      <div class="card"><div class="k">elapsed</div><div class="v mono">__ELAPSED__s</div></div>
    </div>

    <section>
      <h2>Resolved packages</h2>
      <table>
        <thead><tr><th>Package</th><th>Version</th></tr></thead>
        <tbody>__ROWS__</tbody>
      </table>
    </section>

    <section>
      <h2>Command output</h2>
      <pre>__RAW__</pre>
    </section>

    <footer>dbt deps inside the fx-macro-platform container · refreshes every __REFRESH__s</footer>
  </div>
</body>
</html>
"""
    return (
        tpl
        .replace("__REFRESH__", str(REFRESH_SECONDS))
        .replace("__STATUS_CLASS__", status_class)
        .replace("__STATUS_TEXT__", html.escape(status_text))
        .replace("__DBT_VERSION__", html.escape(dbt_version))
        .replace("__HOST__", html.escape(socket.gethostname() or "container"))
        .replace("__TS__", html.escape(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        .replace("__ELAPSED__", f"{elapsed:.1f}")
        .replace("__ROWS__", rows)
        .replace("__RAW__", html.escape(raw))
    )


def serve() -> None:
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            pass

    os.chdir(REPORT_DIR)
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), QuietHandler)
    print(f"[dbt-deps] serving on :{PORT} from {REPORT_DIR}", flush=True)
    httpd.serve_forever()


def main() -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    threading.Thread(target=serve, daemon=True).start()
    while True:
        rc, raw, elapsed, dbt_version = run_deps()
        clean = strip_ansi(raw)
        packages = read_lock_packages()
        page = build_html(rc, clean, elapsed, dbt_version, packages)

        with open(os.path.join(REPORT_DIR, "deps.log"), "w", encoding="utf-8") as f:
            f.write(clean)
        with open(os.path.join(REPORT_DIR, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)

        print(
            f"[dbt-deps] dbt deps exit={rc} elapsed={elapsed:.1f}s "
            f"packages={len(packages)} dbt={dbt_version}",
            flush=True,
        )
        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    main()
