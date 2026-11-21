#!/usr/bin/env python3
"""Builds README.md and every custom graphic from profile.json.

Look: zine / poster. Paper (or charcoal) cards with a hard offset shadow, one
spray-paint accent colour, system monospace type. Every graphic is generated
twice (assets/light, assets/dark) and swapped with <picture>, so it follows
the viewer's GitHub theme.

Nothing depends on third-party image services and no fonts are embedded.
GitHub data comes from the API (GITHUB_TOKEN).
If an API call fails, the previous graphic is kept instead of being replaced
by a placeholder. Standard library only.
"""
import hashlib
import html
import json
import os
import random
import textwrap
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

root = Path(__file__).parent
p = json.loads((root / "profile.json").read_text())
gh = p["github_username"]

THEMES = {
    "light": dict(bg="#f4efe6", ink="#1b1a17", muted="#6f6a5e", faint="#d9d2c3", accent="#b0001e"),
    "dark": dict(bg="#171614", ink="#efe9dc", muted="#a09a8c", faint="#38352f", accent="#e8203a"),
}
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono','DejaVu Sans Mono',monospace"
SH = 6        # hard shadow offset on cards
FULL = 820    # full-width graphic
HALF = 400    # half-width graphic (two per row)


# ---------------- svg primitives ----------------
def rgb(hex_):
    h = hex_.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def mix(a, b, k):
    """Opaque blend of colour a toward b (k=0 is a, k=1 is b)."""
    ca, cb = rgb(a), rgb(b)
    return "#" + "".join(f"{round((x + (y - x) * k) * 255):02x}" for x, y in zip(ca, cb))


def levels(t):
    """Five solid heatmap shades, so reds stay the same hue at every level."""
    return [t["faint"]] + [mix(t["faint"], t["accent"], k) for k in (.4, .65, .85, 1)]


def txt(t, x, y, s, size=15, color="ink", weight=400, anchor="start", extra=""):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{t.get(color, color)}" text-anchor="{anchor}" {extra}>{escape(str(s))}</text>')


def svg(w, h, inner, title="", defs=""):
    t = f"<title>{escape(title)}</title>" if title else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">'
            f'{t}{defs}{inner}</svg>')


def grain(t):
    r, g, b = rgb(t["ink"])
    return ('<defs><filter id="g" x="0" y="0" width="100%" height="100%">'
            '<feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="4"/>'
            f'<feColorMatrix values="0 0 0 0 {r:.3f}  0 0 0 0 {g:.3f}  0 0 0 0 {b:.3f}  0 0 0 .09 0"/>'
            '</filter></defs>')


def card(t, w, content_h, body, title="", shadow=SH):
    """A card with a hard offset shadow. Body coordinates start at the card's top-left."""
    h = content_h + shadow + 2
    cw, ch = w - shadow - 2, content_h
    inner = (f'<rect x="{1 + shadow}" y="{1 + shadow}" width="{cw}" height="{ch}" fill="{t["ink"]}"/>'
             f'<rect x="1" y="1" width="{cw}" height="{ch}" fill="{t["bg"]}" stroke="{t["ink"]}" stroke-width="2"/>'
             f'<rect x="1" y="1" width="{cw}" height="{ch}" filter="url(#g)"/>'
             f'<g transform="translate(1,1)">{body}</g>')
    return svg(w, h, inner, title, grain(t))


def dashed(t, x1, x2, y):
    return f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{t["faint"]}" stroke-width="1.5" stroke-dasharray="2 4"/>'


def clip(s, n):
    s = str(s)
    return s if len(s) <= n else s[: n - 3].rstrip() + "..."


# ---------------- GitHub data ----------------
Q_REPOS = ("query($u:String!){user(login:$u){followers{totalCount} "
           "repositories(ownerAffiliation:OWNER,isFork:false,first:100){totalCount nodes{stargazerCount primaryLanguage{name}}}}}")
Q_CONTRIB = ("query($u:String!){user(login:$u){contributionsCollection{totalCommitContributions "
             "totalPullRequestContributions totalIssueContributions contributionCalendar{totalContributions "
             "weeks{contributionDays{contributionCount date weekday}}}}}}")
Q_PINNED = ("query($u:String!){user(login:$u){pinnedItems(first:6,types:REPOSITORY)"
            "{nodes{... on Repository{name description stargazerCount forkCount primaryLanguage{name}}}}}}")
TOKEN = os.environ.get("GITHUB_TOKEN")


def _open(req):
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def gql(name, query):
    if not TOKEN:
        print(f"[{name}] skipped: no GITHUB_TOKEN")
        return None
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"u": gh}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        body = _open(req)
    except Exception as e:
        detail = getattr(e, "read", lambda: b"")().decode()[:300]
        print(f"[{name}] FAILED: {e} {detail}")
        return None
    if body.get("errors"):
        print(f"[{name}] GraphQL errors: {json.dumps(body['errors'])[:400]}")
    user = (body.get("data") or {}).get("user")
    print(f"[{name}] {'ok' if user else 'no data'}")
    return user


def rest(path):
    headers = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return _open(urllib.request.Request(f"https://api.github.com{path}", headers=headers))


def collect():
    d = dict(followers=None, repo_count=None, repos=None, commits=None, prs=None,
             issues=None, calendar=None, pins=None, events=None)
    u = gql("repos", Q_REPOS)
    if u:
        d["followers"] = u["followers"]["totalCount"]
        d["repo_count"] = u["repositories"]["totalCount"]
        d["repos"] = [(n["stargazerCount"], (n["primaryLanguage"] or {}).get("name"))
                      for n in u["repositories"]["nodes"]]
    else:
        try:
            info = rest(f"/users/{gh}")
            lst = rest(f"/users/{gh}/repos?per_page=100&type=owner")
            d["followers"], d["repo_count"] = info["followers"], info["public_repos"]
            d["repos"] = [(r["stargazers_count"], r["language"]) for r in lst if not r["fork"]]
            print("[repos] REST fallback ok")
        except Exception as e:
            print("[repos] REST fallback FAILED:", e)
    u = gql("contributions", Q_CONTRIB)
    if u:
        c = u["contributionsCollection"]
        d["commits"] = c["totalCommitContributions"]
        d["prs"] = c["totalPullRequestContributions"]
        d["issues"] = c["totalIssueContributions"]
        cal = c["contributionCalendar"]
        d["calendar"] = dict(total=cal["totalContributions"],
                             weeks=[w["contributionDays"] for w in cal["weeks"]])
    u = gql("pinned", Q_PINNED)
    if u:
        d["pins"] = [{"repo": n["name"], "description": n["description"] or "no description yet",
                      "language": (n["primaryLanguage"] or {}).get("name"),
                      "stars": n["stargazerCount"], "forks": n["forkCount"]}
                     for n in u["pinnedItems"]["nodes"] if n]
    try:
        d["events"] = rest(f"/users/{gh}/events/public?per_page=50")
        print("[events] ok")
    except Exception as e:
        print("[events] FAILED:", e)
    return d


def streaks(calendar):
    counts = [day["contributionCount"] for week in calendar["weeks"] for day in week]
    best = run = 0
    for c in counts:
        run = run + 1 if c else 0
        best = max(best, run)
    cur, i = 0, len(counts) - 1
    if i >= 0 and counts[i] == 0:  # today may not have happened yet
        i -= 1
    while i >= 0 and counts[i]:
        cur += 1
        i -= 1
    return cur, best


# ---------------- cards ----------------
def status_card(t):
    s = p["status"]
    rows = [("working on", s["working_on"]), ("learning", s["learning"]),
            ("ask me about", s["ask_me_about"]), ("based in", s["based_in"])]
    cw = FULL - SH - 2
    b = f'<rect x="0" y="0" width="{cw}" height="32" fill="{t["ink"]}"/>'
    for i, col in enumerate((t["accent"], t["muted"], t["muted"])):
        b += f'<circle cx="{20 + i * 16}" cy="16" r="4.5" fill="{col}"/>'
    b += txt(t, 82, 21, f"~/{p['github_username']}", 13, t["bg"], 700)
    for i, (k, v) in enumerate(rows):
        y = 64 + i * 30
        b += txt(t, 24, y, k, 14, "muted") + txt(t, 190, y, clip(v, 64), 15, "ink", 700)
        if i < len(rows) - 1:
            b += dashed(t, 24, cw - 24, y + 10)
    return card(t, FULL, 64 + (len(rows) - 1) * 30 + 24, b, "Status")


def pin_card(t, r):
    cw = HALF - SH - 2
    b = f'<rect x="24" y="24" width="12" height="12" fill="{t["accent"]}"/>'
    b += txt(t, 46, 36, clip(r["repo"], 26), 18, "ink", 700)
    for i, line in enumerate(textwrap.wrap(r["description"], 40)[:3]):
        b += txt(t, 24, 68 + i * 20, line, 14, "muted")
    b += dashed(t, 24, cw - 24, 124)
    if r.get("language"):
        b += f'<circle cx="30" cy="146" r="5" fill="{t["accent"]}"/>' + txt(t, 42, 151, clip(r["language"], 14), 13, "muted")
    meta = "  ".join(x for x in (f'stars {r["stars"]}' if r.get("stars") is not None else "",
                                 f'forks {r["forks"]}' if r.get("forks") is not None else "") if x)
    b += txt(t, cw - 24, 151, meta, 13, "muted", anchor="end")
    return card(t, HALF, 166, b, r["repo"])


def stack_card(t):
    icons = json.loads((root / "icons.json").read_text())
    cw = FULL - SH - 2
    size, pitch = 32, 84
    b = ""
    for row, (label, group) in enumerate((("LANGUAGES", p["skills"]["languages"]), ("TOOLS", p["skills"]["tools"]))):
        top = 34 + row * 104
        b += txt(t, 24, top, label, 12, "muted", 700, extra='letter-spacing="2"')
        b += dashed(t, 24 + len(label) * 9 + 8, cw - 24, top - 4)
        for i, (name, slug) in enumerate(group):
            x, y = 28 + i * pitch, top + 14
            if slug in icons:
                b += (f'<g transform="translate({x},{y}) scale({size / 24})"><title>{escape(name)}</title>'
                      f'<path d="{icons[slug]}" fill="{t["ink"]}"/></g>')
            else:
                b += (f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="3" fill="none" '
                      f'stroke="{t["ink"]}" stroke-width="2"/>' + txt(t, x + size / 2, y + 21, name[:3].upper(), 12, "ink", 700, "middle"))
            b += txt(t, x + size / 2, y + size + 20, name, 11, "muted", anchor="middle")
    return card(t, FULL, 240, b, "Languages and tools")


def stats_card(t, d):
    stars = sum(x[0] for x in d["repos"]) if d["repos"] is not None else None
    rows = [("repositories", d["repo_count"]), ("stars earned", stars), ("commits, past year", d["commits"]),
            ("pull requests", d["prs"]), ("issues", d["issues"]), ("followers", d["followers"])]
    cw = HALF - SH - 2
    b = txt(t, 24, 36, "STATS", 12, "muted", 700, extra='letter-spacing="2"')
    for i, (k, v) in enumerate(rows):
        y = 68 + i * 30
        b += txt(t, 24, y, k, 14) + txt(t, cw - 24, y, "--" if v is None else v, 15, "ink", 700, "end")
        b += dashed(t, 24, cw - 24, y + 8)
    return card(t, HALF, 244, b, "GitHub stats")


def langs_card(t, d):
    cw = HALF - SH - 2
    b = txt(t, 24, 36, "TOP LANGUAGES", 12, "muted", 700, extra='letter-spacing="2"')
    cnt = Counter(l for _, l in (d["repos"] or []) if l)
    tot = sum(cnt.values())
    langs = [(k, v * 100 / tot) for k, v in cnt.most_common(6)] if tot else []
    if not langs:
        b += txt(t, 24, 72, "no language data yet", 14, "muted")
    for i, (k, pct) in enumerate(langs):
        y = 68 + i * 30
        b += txt(t, 24, y, k, 14) + txt(t, cw - 24, y, f"{pct:.0f}%", 14, "muted", anchor="end")
        b += f'<rect x="24" y="{y + 7}" width="{cw - 48}" height="6" fill="{t["faint"]}"/>'
        b += (f'<rect x="24" y="{y + 7}" width="{max(4, (cw - 48) * pct / 100):.1f}" height="6" '
              f'fill="{t["accent"]}"/>')
    return card(t, HALF, 244, b, "Top languages")


def heatmap_card(t, d):
    cal = d["calendar"]
    cw = FULL - SH - 2
    weeks = [w for w in cal["weeks"] if w]
    cur, best = streaks(cal)
    flat = [day["contributionCount"] for w in weeks for day in w]
    peak = max(flat + [1])
    cell, pitch, y0 = 11, 14, 74
    x0 = (cw - len(weeks) * pitch + (pitch - cell)) / 2
    b = txt(t, 24, 36, "CONTRIBUTIONS", 12, "muted", 700, extra='letter-spacing="2"')
    b += txt(t, cw - 24, 36, f'{cal["total"]} in the past year   streak {cur}d   best {best}d', 13, "muted", anchor="end")
    months = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
    last_m, last_x = None, -99
    for i, w in enumerate(weeks):
        x = x0 + i * pitch
        m = int(w[0]["date"][5:7])
        if m != last_m and x - last_x >= 36:
            b += txt(t, f"{x:.1f}", 62, months[m - 1], 10, "muted")
            last_x = x
        last_m = m
        for day in w:
            c = day["contributionCount"]
            lvl = 0 if c == 0 else min(4, max(1, -(-4 * c // peak)))
            fill = levels(t)[lvl]
            b += (f'<rect x="{x:.1f}" y="{y0 + day["weekday"] * pitch}" width="{cell}" height="{cell}" '
                  f'fill="{fill}"><title>{day["date"]}: {c}</title></rect>')
    ly = y0 + 7 * pitch + 14
    lx = cw - 24
    b += txt(t, lx, ly + 9, "more", 10, "muted", anchor="end")
    for i, col in enumerate(reversed(levels(t))):
        b += f'<rect x="{lx - 40 - i * 15}" y="{ly}" width="{cell}" height="{cell}" fill="{col}"/>'
    b += txt(t, lx - 40 - 4 * 15 - 8, ly + 9, "less", 10, "muted", anchor="end")
    return card(t, FULL, ly + cell + 22, b, "Contribution activity, past year")


def ago(iso):
    secs = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds())
    for n, unit in ((86400 * 30, "mo"), (86400, "d"), (3600, "h"), (60, "m")):
        if secs >= n:
            return f"{int(secs // n)}{unit} ago"
    return "just now"


def describe(ev):
    """(verb, repo) for the event types worth showing, else None."""
    k, pl = ev.get("type"), ev.get("payload", {})
    repo = ev["repo"]["name"].split("/", 1)[-1]
    if k == "PushEvent":
        n = pl.get("size") or len(pl.get("commits", []))
        return (f"pushed {n} commit{'s' if n != 1 else ''}" if n else "pushed"), repo
    if k == "CreateEvent":
        return f"created {pl.get('ref_type', 'repo')}", repo
    if k == "PullRequestEvent":
        pr = pl.get("pull_request", {})
        act = "merged PR" if pr.get("merged") else f"{pl.get('action', 'opened')} PR"
        return act, repo
    if k == "IssuesEvent":
        return f"{pl.get('action', 'opened')} issue", repo
    if k == "IssueCommentEvent":
        return "commented", repo
    if k == "WatchEvent":
        return "starred", repo
    if k == "ForkEvent":
        return "forked", repo
    if k == "ReleaseEvent":
        return "released", repo
    return None


def recent_items(events, n=5):
    items = []
    for ev in events or []:
        d = describe(ev)
        if not d:
            continue
        if items and items[-1][:2] == d:  # collapse repeats
            continue
        items.append((*d, ago(ev["created_at"])))
        if len(items) == n:
            break
    return items


def recent_card(t, events):
    cw = FULL - SH - 2
    items = recent_items(events)
    b = txt(t, 24, 36, "RECENT ACTIVITY", 12, "muted", 700, extra='letter-spacing="2"')
    if not items:
        b += txt(t, 24, 72, "no public activity yet", 14, "muted")
        return card(t, FULL, 100, b, "Recent GitHub activity")
    for i, (verb, repo, when) in enumerate(items):
        y = 68 + i * 30
        b += f'<rect x="24" y="{y - 10}" width="8" height="8" fill="{t["accent"]}"/>'
        b += txt(t, 44, y, verb, 14, "muted") + txt(t, 220, y, clip(repo, 40), 15, "ink", 700)
        b += txt(t, cw - 24, y, when, 13, "muted", anchor="end")
        if i < len(items) - 1:
            b += dashed(t, 24, cw - 24, y + 10)
    return card(t, FULL, 68 + (len(items) - 1) * 30 + 26, b, "Recent GitHub activity")


# ---------------- headings, tagline, divider, socials ----------------
def heading_svg(t, num, title):
    w, h = FULL, 48
    n = len(title)
    tw = n * 19
    inner = (f'<rect x="2" y="6" width="36" height="36" fill="{t["accent"]}"/>'
             + txt(t, 20, 31, f"{num:02d}", 16, t["bg"], 700, "middle")
             + txt(t, 54, 33, title, 26, "ink", 700, extra=f'textLength="{tw}" lengthAdjust="spacing"')
             + f'<line x1="{54 + tw + 16}" y1="24" x2="{w - 10}" y2="24" stroke="{t["ink"]}" stroke-width="2"/>'
             + f'<rect x="{w - 12}" y="20" width="8" height="8" fill="{t["accent"]}"/>')
    return svg(w, h, inner, title)


def tagline_svg(t, s):
    w, h, fs = FULL, 56, 22
    cw = 0.6 * fs
    n = len(s)
    tw = n * cw
    x0 = (w - tw) / 2
    vals = ";".join(f"{cw * k:.1f}" for k in range(n + 1))
    keys = ";".join(f"{k / n:.3f}" for k in range(n + 1))
    inner = (f'<clipPath id="c"><rect x="{x0:.1f}" y="0" height="{h}" width="0">'
             f'<animate attributeName="width" dur="2.4s" begin="0.3s" fill="freeze" calcMode="discrete" values="{vals}" keyTimes="{keys}"/></rect></clipPath>'
             + txt(t, f"{x0:.1f}", 36, s, fs, "ink", 400, extra=f'textLength="{tw:.1f}" lengthAdjust="spacing" clip-path="url(#c)"')
             + f'<rect x="{x0 + tw + 4:.1f}" y="14" width="12" height="26" fill="{t["accent"]}">'
               '<animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>')
    return svg(w, h, inner, s)


def divider_svg(t):
    rnd = random.Random(11)
    w, h = FULL, 28

    def wobble(x0, x1):
        pts = [(x, 14 + rnd.uniform(-1.4, 1.4)) for x in range(x0, x1 + 1, 14)]
        return "M" + " L".join(f"{x},{y:.1f}" for x, y in pts)
    inner = (f'<path d="{wobble(10, 372)}" stroke="{t["ink"]}" stroke-width="2" fill="none" stroke-linecap="round"/>'
             + "".join(f'<circle cx="{394 + i * 16}" cy="14" r="2.6" fill="{t["accent"]}"/>' for i in range(3))
             + f'<path d="{wobble(448, 810)}" stroke="{t["ink"]}" stroke-width="2" fill="none" stroke-linecap="round"/>')
    return svg(w, h, inner)


def email_glyph(t):
    return (f'<g fill="none" stroke="{t["ink"]}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="2.5" y="5" width="19" height="14" rx="1.5"/><path d="M3 6.5l9 6.8 9-6.8"/></g>')


def globe_glyph(t):
    return (f'<g fill="none" stroke="{t["ink"]}" stroke-width="1.8" stroke-linecap="round">'
            '<circle cx="12" cy="12" r="9.5"/><ellipse cx="12" cy="12" rx="4.2" ry="9.5"/>'
            '<path d="M2.5 12h19M4 7.2h16M4 16.8h16"/></g>')


def social_slug(name):
    return "".join(ch for ch in name.lower() if ch.isalnum())


def social_width(name):
    return int(16 + 22 + 10 + len(name) * 9.5 + 18 + 4 + 2)


def social_svg(t, name):
    icons = json.loads((root / "icons.json").read_text())
    slug = social_slug(name)
    if slug == "email":
        glyph = email_glyph(t)
    elif slug in ("website", "site", "web"):
        glyph = globe_glyph(t)
    elif slug in icons:
        glyph = f'<path d="{icons[slug]}" fill="{t["ink"]}"/>'
    else:
        glyph = ""
    w = social_width(name)
    label = name.upper()
    b = f'<g transform="translate(16,9) scale({22 / 24})">{glyph}</g>' if glyph else ""
    b += txt(t, 48, 25, label, 13, "ink", 700, extra=f'textLength="{len(label) * 9.5:.1f}" lengthAdjust="spacing"')
    return card(t, w, 40, b, name, shadow=4)


# ---------------- output helpers ----------------
EMITTED = set()


def emit(name, fn, fresh=True):
    """Write a graphic for every theme. With fresh=False, keep any existing file."""
    EMITTED.add(name)
    for tn, t in THEMES.items():
        path = root / "assets" / tn / name
        if fresh or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fn(t))


def ver(path):
    """Short content hash, so GitHub's image cache refetches whenever a graphic changes."""
    try:
        return hashlib.md5(Path(path).read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"


def pic(name, alt, width="100%", link=None):
    a = html.escape(alt, quote=True)
    vd = ver(root / "assets" / "dark" / name)
    vl = ver(root / "assets" / "light" / name)
    im = (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/dark/{name}?v={vd}">'
          f'<img src="assets/light/{name}?v={vl}" width="{width}" alt="{a}" /></picture>')
    return f'<a href="{html.escape(link, quote=True)}">{im}</a>' if link else im


def pic_png(name, alt, width):
    a = html.escape(alt, quote=True)
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/img/{name}-dark.png">'
            f'<img src="assets/img/{name}-light.png" width="{width}" alt="{a}" /></picture>')


def load_cache():
    f = root / "data" / "cache.json"
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}


def save_cache(c):
    f = root / "data" / "cache.json"
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps(c, indent=2, sort_keys=True) + "\n")


SECTIONS = [("about", "ABOUT"), ("projects", "PROJECTS"), ("stack", "STACK"),
            ("latest", "RECENT"), ("activity", "ACTIVITY"), ("contact", "CONTACT")]


# ---------------- build ----------------
def build(d):
    cache = load_cache()

    emit("tagline.svg", lambda t: tagline_svg(t, p["tagline"]))
    emit("divider.svg", divider_svg)
    for i, (slug, title) in enumerate(SECTIONS, 1):
        emit(f"h-{slug}.svg", lambda t, i=i, title=title: heading_svg(t, i, title))
    emit("status.svg", status_card)
    emit("stack.svg", stack_card)
    emit("stats.svg", lambda t: stats_card(t, d), fresh=d["repos"] is not None)
    emit("langs.svg", lambda t: langs_card(t, d), fresh=d["repos"] is not None)
    if d["calendar"]:
        emit("heatmap.svg", lambda t: heatmap_card(t, d))
    else:
        EMITTED.add("heatmap.svg")  # keep the last good one
    emit("latest.svg", lambda t: recent_card(t, d["events"]), fresh=d["events"] is not None)

    # projects: live pins, else last good pins, else the fallback list from profile.json
    src = p.get("projects_source", {})
    mx = src.get("max", 4)
    if d["pins"] and src.get("mode") == "pinned":
        projects = d["pins"][:mx]
        cache["pins"] = projects
        save_cache(cache)
    else:
        projects = cache.get("pins") or p.get("projects_fallback", [])
    projects = [r for r in projects if not r["repo"].startswith("PROJECT_")][:mx]

    for tn in THEMES:
        for old in (root / "assets" / tn).glob("pin-*.svg"):
            old.unlink()
    pins = []
    for i, r in enumerate(projects, 1):
        emit(f"pin-{i}.svg", lambda t, r=r: pin_card(t, r))
        pins.append(pic(f"pin-{i}.svg", f'{r["repo"]}: {r["description"]}', "49%", f"https://github.com/{gh}/{r['repo']}"))

    for tn in THEMES:
        for old in (root / "assets" / tn).glob("social-*.svg"):
            old.unlink()
    socials = []
    for name, url in p["links"].items():
        emit(f"social-{social_slug(name)}.svg", lambda t, name=name: social_svg(t, name))
        socials.append(pic(f"social-{social_slug(name)}.svg", name, str(social_width(name)), url))

    def head(slug, title):
        return pic(f"h-{slug}.svg", title)

    parts = [
        '<div align="center">\n',
        pic_png("logo", p["name"].upper(), 300),
        "",
        pic("tagline.svg", p["tagline"]),
        "\n</div>\n",
        pic("divider.svg", ""),
        "",
        head("about", "About"),
        "",
        p["bio"],
        "",
        pic("status.svg", "Status"),
        "",
    ]
    if pins:
        parts += [head("projects", "Projects"), ""]
        for i in range(0, len(pins), 2):
            parts += ["\n".join(pins[i:i + 2]), ""]
    parts += [head("stack", "Stack"), "", pic("stack.svg", "Languages and tools"), "",
              head("latest", "Recent"), "",
              pic("latest.svg", "Recent GitHub activity", link=f"https://github.com/{gh}"), "",
              head("activity", "Activity"), ""]
    if (root / "assets" / "light" / "heatmap.svg").exists():
        parts += [pic("heatmap.svg", "Contribution activity, past year"), ""]
    parts += ["\n".join([pic("stats.svg", "GitHub stats", "49%"), pic("langs.svg", "Top languages", "49%")]), "",
              head("contact", "Contact"), "", "\n".join(socials), "",
              pic("divider.svg", ""), "", '<div align="center">\n',
              pic_png("ascii", "", 200), "", f"<sub>{html.escape(p['footer'])}</sub>", "\n</div>", ""]
    (root / "README.md").write_text("\n".join(parts))
    for tn in THEMES:  # drop graphics nothing generates any more
        for f in (root / "assets" / tn).glob("*.svg"):
            if f.name not in EMITTED:
                f.unlink()


def main():
    d = collect()
    build(d)
    print("built:", "pinned repos" if d["pins"] else "cached/fallback projects", "|",
          "stats" if d["repos"] else "no stats", "|", "heatmap" if d["calendar"] else "no heatmap")


if __name__ == "__main__":
    main()
