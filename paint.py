#!/usr/bin/env python3
"""Applies pixel-wall requests. Every open issue titled "paint: ..." is read, strictly
validated, applied to data/canvas.json, answered and closed. Issue text is never
executed or interpolated anywhere; only a column, row and palette name are accepted.
Sweeping all open issues (not just the triggering one) means a skipped run loses nothing."""
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

import canvas

REPO, TOKEN = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")


def call(method, path, data=None):
    req = urllib.request.Request(
        f"https://api.github.com{path}", method=method,
        data=None if data is None else json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
    return json.loads(body) if body else None


def field(body, label):
    m = re.search(rf"###[ \t]*{label}[ \t]*(?:\r?\n)+[ \t]*([^\r\n]+)", body or "")
    return m.group(1).strip() if m else None


def handle(state, issue, now):
    """Returns (applied, message). Mutates state only when the request is valid."""
    login = issue["user"]["login"]
    col, row, colour = (field(issue.get("body"), k) for k in ("Column", "Row", "Colour"))
    if not (col and col.isdigit() and row and row.isdigit() and colour in canvas.NAMES):
        return False, "I couldn't read that request. Please use the form: pick a column, a row and a colour."
    x, y = int(col), int(row)
    if not (1 <= x <= canvas.W and 1 <= y <= canvas.H):
        return False, f"That's off the wall. Columns run 1-{canvas.W} and rows 1-{canvas.H}."
    last = state["cooldown"].get(login)
    if last:
        wait = canvas.COOLDOWN - (now - datetime.fromisoformat(last)).total_seconds()
        if wait > 0:
            return False, f"Easy there. You can paint again in about {int(wait // 60) + 1} minute(s)."
    canvas.paint(state, x, y, colour, login, now)
    return True, f"Painted column {x}, row {y} in {colour}. It shows on the profile within a minute or two."


def main():
    if not (TOKEN and REPO):
        print("[paint] skipped: no token or repo")
        return
    issues = call("GET", f"/repos/{REPO}/issues?state=open&per_page=50&sort=created&direction=asc")
    todo = [i for i in issues if "pull_request" not in i and i["title"].lower().startswith("paint:")]
    state, changed = canvas.load(), False
    for issue in todo:
        ok, msg = handle(state, issue, datetime.now(timezone.utc))
        changed |= ok
        try:
            call("POST", f"/repos/{REPO}/issues/{issue['number']}/comments", {"body": msg})
            call("PATCH", f"/repos/{REPO}/issues/{issue['number']}",
                 {"state": "closed", "state_reason": "completed" if ok else "not_planned"})
        except Exception as e:
            print(f"[paint] #{issue['number']} reply failed: {e}")
        print(f"[paint] #{issue['number']}: {'ok' if ok else 'rejected'}")
    if changed:
        canvas.save(state)


if __name__ == "__main__":
    main()
