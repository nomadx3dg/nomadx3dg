#!/usr/bin/env python3
"""Builds README.md and the stat/project cards from profile.json.

Everything is drawn locally as SVG, so nothing depends on third-party image
services. Data comes from the GitHub API (GITHUB_TOKEN) and Last.fm
(LASTFM_API_KEY); without them, placeholders / fallbacks are used.
Standard library only.
"""
import json, os, textwrap, urllib.parse, urllib.request
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

root = Path(__file__).parent
p = json.loads((root / "profile.json").read_text())
gh = p["github_username"]
FONT = "'Courier New', Courier, monospace"
W = 480

QUERY = """query($u:String!){user(login:$u){
 followers{totalCount}
 repositories(ownerAffiliation:OWNER,isFork:false,first:100,privacy:PUBLIC){totalCount nodes{stargazerCount primaryLanguage{name}}}
 contributionsCollection{totalCommitContributions totalPullRequestContributions totalIssueContributions}
 pinnedItems(first:6,types:REPOSITORY){nodes{... on Repository{name description stargazerCount forkCount primaryLanguage{name}}}}
}}"""


def github_data():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"u": gh}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)["data"]["user"]
    except Exception as e:
        print("GitHub lookup failed:", e)
        return None


# ---------- svg helpers ----------
def card(h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}">'
            f'<rect x=".5" y=".5" width="{W-1}" height="{h-1}" rx="6" fill="#000" stroke="#333"/>'
            f'{body}</svg>')


def text(x, y, s, size=15, fill="#fff", weight="400", anchor="start"):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(str(s))}</text>')


def stats_svg(u):
    if u:
        c = u["contributionsCollection"]
        stars = sum(n["stargazerCount"] for n in u["repositories"]["nodes"])
        rows = [("repositories", u["repositories"]["totalCount"]), ("stars earned", stars),
                ("commits, past year", c["totalCommitContributions"]),
                ("pull requests", c["totalPullRequestContributions"]),
                ("issues", c["totalIssueContributions"]), ("followers", u["followers"]["totalCount"])]
    else:
        rows = [(k, "--") for k in ("repositories", "stars earned", "commits, past year",
                                    "pull requests", "issues", "followers")]
    h = 56 + len(rows) * 28
    b = text(20, 32, "STATS", 13, "#888", "700")
    for i, (k, v) in enumerate(rows):
        y = 64 + i * 28
        b += text(20, y, k) + text(W - 20, y, v, 15, "#fff", "700", "end")
    return card(h, b)


def langs_svg(u):
    b = text(20, 32, "TOP LANGUAGES", 13, "#888", "700")
    langs = []
    if u:
        cnt = Counter(n["primaryLanguage"]["name"] for n in u["repositories"]["nodes"] if n["primaryLanguage"])
        tot = sum(cnt.values())
        langs = [(k, v * 100 / tot) for k, v in cnt.most_common(6)]
    if not langs:
        return card(80, b + text(20, 58, "fills in after the first Action run", 14, "#888"))
    shades = ["#ffffff", "#dddddd", "#bbbbbb", "#999999", "#777777", "#555555"]
    for i, (k, pct) in enumerate(langs):
        y = 64 + i * 30
        b += text(20, y, k, 14) + text(W - 20, y, f"{pct:.0f}%", 14, "#aaa", "400", "end")
        b += f'<rect x="20" y="{y+7}" width="{W-40}" height="5" rx="2.5" fill="#1a1a1a"/>'
        b += f'<rect x="20" y="{y+7}" width="{max(4,(W-40)*pct/100):.1f}" height="5" rx="2.5" fill="{shades[i]}"/>'
    return card(56 + len(langs) * 30 + 4, b)


def pin_svg(r):
    b = text(20, 34, r["repo"], 17, "#fff", "700")
    for i, line in enumerate(textwrap.wrap(r["description"], 50)[:2]):
        b += text(20, 62 + i * 20, line, 14, "#aaa")
    meta = "   ".join(x for x in (r.get("language"), f'stars {r["stars"]}' if r.get("stars") is not None else None,
                                  f'forks {r["forks"]}' if r.get("forks") is not None else None) if x)
    b += text(20, 112, meta, 13, "#888")
    return card(128, b)


# ---------- music ----------
def now_playing():
    m = p["music"]
    key = os.environ.get("LASTFM_API_KEY")
    if not key or m["lastfm_user"].startswith("YOUR_"):
        return m["fallback"], None
    q = urllib.parse.urlencode({"method": "user.getrecenttracks", "user": m["lastfm_user"],
                                "api_key": key, "format": "json", "limit": 1})
    try:
        with urllib.request.urlopen(f"https://ws.audioscrobbler.com/2.0/?{q}", timeout=15) as r:
            t = json.load(r)["recenttracks"]["track"][0]
        label = "now playing" if t.get("@attr", {}).get("nowplaying") == "true" else "last played"
        return f'{label}   {t["artist"]["#text"]} - {t["name"]}', t.get("url")
    except Exception:
        return m["fallback"], None


def stack_svg():
    icons = json.loads((root / "icons.json").read_text())
    size, pitch = 30, 48
    body = ""
    for row, group in enumerate((p["skills"]["languages"], p["skills"]["tools"])):
        y = 13 + row * 44
        for i, (name, slug) in enumerate(group):
            x = 8 + i * pitch
            if slug in icons:
                body += (f'<g transform="translate({x},{y}) scale({size/24})"><title>{escape(name)}</title>'
                         f'<path d="{icons[slug]}" fill="#fff"/></g>')
            else:
                body += text(x + size / 2, y + 21, name[:4].upper(), 13, "#fff", "700", "middle")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="100" viewBox="0 0 {W} 100">'
            f'<rect width="100%" height="100%" fill="#000"/>{body}</svg>')


def img(slug, alt):
    return f'<img src="assets/h-{slug}.svg" width="100%" alt="{alt}" />'


# ---------- build ----------
u = github_data()
(root / "assets").mkdir(exist_ok=True)
(root / "assets/stats.svg").write_text(stats_svg(u))
(root / "assets/langs.svg").write_text(langs_svg(u))
(root / "assets/stack.svg").write_text(stack_svg())

src = p.get("projects_source", {})
projects = []
if u and src.get("mode") == "pinned":
    for n in u["pinnedItems"]["nodes"][: src.get("max", 3)]:
        if n:
            projects.append({"repo": n["name"], "description": n["description"] or "no description yet",
                             "language": (n["primaryLanguage"] or {}).get("name"),
                             "stars": n["stargazerCount"], "forks": n["forkCount"]})
projects = projects or p["projects_fallback"]
for old in (root / "assets").glob("pin-*.svg"):
    old.unlink()
pins = []
for i, r in enumerate(projects):
    (root / f"assets/pin-{i+1}.svg").write_text(pin_svg(r))
    pins.append(f'<a href="https://github.com/{gh}/{r["repo"]}"><img src="assets/pin-{i+1}.svg" width="{W}" alt="{r["repo"]}" /></a>')

track, track_url = now_playing()
track_md = f"```\n{track}\n```" + (f"\n[Open on Last.fm]({track_url})" if track_url else "")
s = p["status"]
links = " / ".join(f"[{k}]({v})" for k, v in p["links"].items())

readme = f"""<div align="center">

<img src="assets/nomad-logo.jpg" width="320" alt="{p['name'].upper()}" />

<img src="assets/tagline.svg" width="100%" alt="{p['tagline']}" />

</div>

<img src="assets/divider.svg" width="100%" alt="" />

{img('about', 'About')}

{p['bio']}

```
working on   {s['working_on']}
learning     {s['learning']}
ask me about {s['ask_me_about']}
based in     {s['based_in']}
```

{img('projects', 'Projects')}

{chr(10).join(pins)}

{img('stack', 'Stack')}

<img src="assets/stack.svg" width="100%" alt="Languages and tools" />

{img('listening', 'Listening')}

{track_md}

<sub>via {p['music']['service']}</sub>

{img('github', 'GitHub')}

<img src="assets/stats.svg" width="{W}" alt="GitHub stats" />

<img src="assets/langs.svg" width="{W}" alt="Top languages" />

{img('contributing', 'Contributing')}

{p['contributing']}

{img('contact', 'Contact')}

{links}

<img src="assets/divider.svg" width="100%" alt="" />

<div align="center">

<img src="assets/nomad-ascii.jpg" width="220" alt="" />

<sub>{p['footer']}</sub>

</div>
"""
(root / "README.md").write_text(readme)
print("built:", "live GitHub data" if u else "placeholders (no token)")
