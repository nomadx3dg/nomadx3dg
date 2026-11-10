#!/usr/bin/env python3
"""Builds README.md plus every custom graphic from profile.json.

Paper theme: warm paper background, ink-black text, typewriter fonts.
Everything is drawn locally as SVG (fonts embedded), so nothing depends on
third-party image services. GitHub data comes from the API (GITHUB_TOKEN),
Last.fm from LASTFM_API_KEY; missing data degrades to placeholders.
Standard library only.
"""
import base64, json, os, random, textwrap, urllib.parse, urllib.request
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

root = Path(__file__).parent
p = json.loads((root / "profile.json").read_text())
gh = p["github_username"]
W = 480
PAPER, INK, MUTED, FAINT = "#f4efe6", "#1b1a17", "#6f6a5e", "#d9d2c3"


# ---------------- fonts & shared svg bits ----------------
def b64(name):
    return base64.b64encode((root / "assets/fonts" / name).read_bytes()).decode()


def face(family, name, weight=400):
    return (f"@font-face{{font-family:'{family}';font-weight:{weight};"
            f"src:url(data:font/woff2;base64,{b64(name)}) format('woff2');}}")


MONO_CSS = face("CP", "courier-400.woff2", 400) + face("CP", "courier-700.woff2", 700)
HEAD_CSS = face("Elite", "elite-caps.woff2")
MONO = "'CP','Courier New',Courier,monospace"
GRAIN = ('<defs><filter id="g" x="0" y="0" width="100%" height="100%">'
         '<feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="4"/>'
         '<feColorMatrix values="0 0 0 0 .1  0 0 0 0 .1  0 0 0 0 .1  0 0 0 .10 0"/></filter></defs>')


def paper(w, h):
    return f'<rect width="{w}" height="{h}" fill="{PAPER}"/><rect width="{w}" height="{h}" filter="url(#g)"/>'


def text(x, y, s, size=15, fill=INK, weight="400", anchor="start"):
    return (f'<text x="{x}" y="{y}" font-family="{MONO}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(str(s))}</text>')


def card(h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}">'
            f'<style>{MONO_CSS}</style>{GRAIN}{paper(W, h)}'
            f'<rect x="1" y="1" width="{W-2}" height="{h-2}" rx="2" fill="none" stroke="{INK}" stroke-width="1.5"/>'
            f'<rect x="5" y="5" width="{W-10}" height="{h-10}" rx="1" fill="none" stroke="{INK}" stroke-width=".5"/>'
            f'{body}</svg>')


# ---------------- GitHub data ----------------
Q_PINNED = ("query($u:String!){user(login:$u){pinnedItems(first:6,types:REPOSITORY)"
            "{nodes{... on Repository{name description stargazerCount forkCount primaryLanguage{name}}}}}}")
Q_REPOS = ("query($u:String!){user(login:$u){followers{totalCount} "
           "repositories(ownerAffiliation:OWNER,isFork:false,first:100){totalCount nodes{stargazerCount primaryLanguage{name}}}}}")
Q_CONTRIB = ("query($u:String!){user(login:$u){contributionsCollection"
             "{totalCommitContributions totalPullRequestContributions totalIssueContributions}}}")
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
    d = {"followers": None, "repo_count": None, "repos": None, "commits": None,
         "prs": None, "issues": None, "pins": None}
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
        d["commits"], d["prs"], d["issues"] = (c["totalCommitContributions"],
                                              c["totalPullRequestContributions"],
                                              c["totalIssueContributions"])
    u = gql("pinned", Q_PINNED)
    if u:
        d["pins"] = [{"repo": n["name"], "description": n["description"] or "no description yet",
                      "language": (n["primaryLanguage"] or {}).get("name"),
                      "stars": n["stargazerCount"], "forks": n["forkCount"]}
                     for n in u["pinnedItems"]["nodes"] if n]
    return d


# ---------------- cards ----------------
def stats_svg(d):
    stars = sum(x[0] for x in d["repos"]) if d["repos"] is not None else None
    rows = [("repositories", d["repo_count"]), ("stars earned", stars),
            ("commits, past year", d["commits"]), ("pull requests", d["prs"]),
            ("issues", d["issues"]), ("followers", d["followers"])]
    b = text(24, 36, "STATS", 12, MUTED, "700")
    for i, (k, v) in enumerate(rows):
        y = 68 + i * 28
        b += text(24, y, k) + text(W - 24, y, "--" if v is None else v, 15, INK, "700", "end")
        b += f'<line x1="24" y1="{y+8}" x2="{W-24}" y2="{y+8}" stroke="{FAINT}" stroke-dasharray="2 4"/>'
    return card(60 + len(rows) * 28 + 8, b)


def langs_svg(d):
    b = text(24, 36, "TOP LANGUAGES", 12, MUTED, "700")
    cnt = Counter(l for _, l in (d["repos"] or []) if l)
    tot = sum(cnt.values())
    langs = [(k, v * 100 / tot) for k, v in cnt.most_common(6)] if tot else []
    if not langs:
        return card(84, b + text(24, 62, "no language data yet", 14, MUTED))
    shades = ["#1b1a17", "#3a3833", "#58554d", "#77736a", "#99948a", "#b9b3a6"]
    for i, (k, pct) in enumerate(langs):
        y = 68 + i * 30
        b += text(24, y, k, 14) + text(W - 24, y, f"{pct:.0f}%", 14, MUTED, "400", "end")
        b += f'<rect x="24" y="{y+7}" width="{W-48}" height="5" fill="{FAINT}"/>'
        b += f'<rect x="24" y="{y+7}" width="{max(4,(W-48)*pct/100):.1f}" height="5" fill="{shades[i]}"/>'
    return card(60 + len(langs) * 30 + 8, b)


def pin_svg(r):
    b = text(24, 38, r["repo"], 17, INK, "700")
    for i, line in enumerate(textwrap.wrap(r["description"], 46)[:2]):
        b += text(24, 66 + i * 20, line, 14, MUTED)
    meta = "   ".join(x for x in (r.get("language"),
                                  f'stars {r["stars"]}' if r.get("stars") is not None else None,
                                  f'forks {r["forks"]}' if r.get("forks") is not None else None) if x)
    b += f'<line x1="24" y1="96" x2="{W-24}" y2="96" stroke="{FAINT}" stroke-dasharray="2 4"/>'
    b += text(24, 118, meta, 13, MUTED)
    return card(134, b)


def stack_svg():
    icons = json.loads((root / "icons.json").read_text())
    size, pitch = 30, 48
    body = ""
    for row, group in enumerate((p["skills"]["languages"], p["skills"]["tools"])):
        y = 18 + row * 44
        for i, (name, slug) in enumerate(group):
            x = 22 + i * pitch
            if slug in icons:
                body += (f'<g transform="translate({x},{y}) scale({size/24})"><title>{escape(name)}</title>'
                         f'<path d="{icons[slug]}" fill="{INK}"/></g>')
            else:
                body += text(x + size / 2, y + 21, name[:4].upper(), 13, INK, "700", "middle")
    return card(112, body)


# ---------------- headings, tagline, divider ----------------
def heading_svg(num, title):
    w, h = 820, 84
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<style>{MONO_CSS}{HEAD_CSS}</style>{GRAIN}{paper(w, h)}'
            f'<circle cx="34" cy="38" r="19" fill="none" stroke="{INK}" stroke-width="1.5"/>'
            f'<circle cx="34" cy="38" r="15.5" fill="none" stroke="{INK}" stroke-width=".6"/>'
            f'<text x="34" y="43" font-family="{MONO}" font-size="14" font-weight="700" fill="{INK}" text-anchor="middle">{num:02d}</text>'
            f'<g transform="rotate(-0.6 70 40)">'
            f'<text x="71" y="55" font-family="Elite,{MONO}" font-size="40" fill="{INK}" opacity=".28" letter-spacing="3">{escape(title)}</text>'
            f'<text x="70" y="54" font-family="Elite,{MONO}" font-size="40" fill="{INK}" letter-spacing="3">{escape(title)}</text></g>'
            f'<line x1="8" y1="73" x2="{w-8}" y2="73" stroke="{INK}" stroke-width="2"/>'
            f'<line x1="8" y1="78" x2="{w-8}" y2="78" stroke="{INK}" stroke-width=".8"/></svg>')


def tagline_svg(txt):
    w, h, fs = 820, 64, 24
    cw = 0.6 * fs
    n = len(txt)
    tw = n * cw
    x0 = (w - tw) / 2
    vals = ";".join(f"{cw*k:.1f}" for k in range(n + 1))
    keys = ";".join(f"{k/n:.3f}" for k in range(n + 1))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<style>{MONO_CSS}</style>{GRAIN}{paper(w, h)}'
            f'<clipPath id="c"><rect x="{x0:.1f}" y="0" height="{h}" width="0">'
            f'<animate attributeName="width" dur="2.6s" begin="0.3s" fill="freeze" calcMode="discrete" values="{vals}" keyTimes="{keys}"/></rect></clipPath>'
            f'<text x="{x0:.1f}" y="40" font-family="{MONO}" font-size="{fs}" fill="{INK}" clip-path="url(#c)">{escape(txt)}</text>'
            f'<rect x="{x0+tw+4:.1f}" y="18" width="13" height="26" fill="{INK}">'
            f'<animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect></svg>')


def divider_svg():
    rnd = random.Random(11)
    w, h = 820, 36

    def wobble(x0, x1):
        pts = [(x, 18 + rnd.uniform(-1.3, 1.3)) for x in range(x0, x1 + 1, 14)]
        return "M" + " L".join(f"{x},{y:.1f}" for x, y in pts)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'{GRAIN}{paper(w, h)}'
            f'<path d="{wobble(20, 372)}" stroke="{INK}" stroke-width="1.6" fill="none" stroke-linecap="round"/>'
            f'<circle cx="394" cy="18" r="2.4" fill="{INK}"/><circle cx="410" cy="18" r="2.4" fill="{INK}"/><circle cx="426" cy="18" r="2.4" fill="{INK}"/>'
            f'<path d="{wobble(448, 800)}" stroke="{INK}" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg>')


# ---------------- music ----------------
def now_playing():
    m = p["music"]
    key = os.environ.get("LASTFM_API_KEY")
    if not key or m["lastfm_user"].startswith("YOUR_"):
        return m["fallback"], None
    q = urllib.parse.urlencode({"method": "user.getrecenttracks", "user": m["lastfm_user"],
                                "api_key": key, "format": "json", "limit": 1})
    try:
        t = _open(urllib.request.Request(f"https://ws.audioscrobbler.com/2.0/?{q}"))["recenttracks"]["track"][0]
        label = "now playing" if t.get("@attr", {}).get("nowplaying") == "true" else "last played"
        return f'{label}: {t["artist"]["#text"]} - {t["name"]}', t.get("url")
    except Exception as e:
        print("[lastfm] FAILED:", e)
        return m["fallback"], None


def img(slug, alt):
    return f'<img src="assets/h-{slug}.svg" width="100%" alt="{alt}" />'


# ---------------- build ----------------
A = root / "assets"
A.mkdir(exist_ok=True)
d = collect()
A.joinpath("stats.svg").write_text(stats_svg(d))
A.joinpath("langs.svg").write_text(langs_svg(d))
A.joinpath("stack.svg").write_text(stack_svg())
A.joinpath("tagline.svg").write_text(tagline_svg(p["tagline"]))
A.joinpath("divider.svg").write_text(divider_svg())
for i, (slug, title) in enumerate([("about", "ABOUT"), ("projects", "PROJECTS"), ("stack", "STACK"),
                                   ("listening", "LISTENING"), ("github", "GITHUB"),
                                   ("contributing", "CONTRIBUTING"), ("contact", "CONTACT")], 1):
    A.joinpath(f"h-{slug}.svg").write_text(heading_svg(i, title))

src = p.get("projects_source", {})
projects = []
if d["pins"] and src.get("mode") == "pinned":
    projects = d["pins"][: src.get("max", 3)]
projects = projects or p["projects_fallback"]
for old in A.glob("pin-*.svg"):
    old.unlink()
pins = []
for i, r in enumerate(projects):
    A.joinpath(f"pin-{i+1}.svg").write_text(pin_svg(r))
    pins.append(f'<a href="https://github.com/{gh}/{r["repo"]}"><img src="assets/pin-{i+1}.svg" width="{W}" alt="{r["repo"]}" /></a>')

track, track_url = now_playing()
track_md = f"**{track}**" + (f"  \n[Open on Last.fm]({track_url})" if track_url else "")
s = p["status"]
links = " / ".join(f"[{k}]({v})" for k, v in p["links"].items())

readme = f"""<div align="center">

<img src="assets/nomad-logo.jpg" width="320" alt="{p['name'].upper()}" />

<img src="assets/tagline.svg" width="100%" alt="{p['tagline']}" />

</div>

<img src="assets/divider.svg" width="100%" alt="" />

{img('about', 'About')}

{p['bio']}

**working on:** {s['working_on']}<br/>
**learning:** {s['learning']}<br/>
**ask me about:** {s['ask_me_about']}<br/>
**based in:** {s['based_in']}

{img('projects', 'Projects')}

{chr(10).join(pins)}

{img('stack', 'Stack')}

<img src="assets/stack.svg" width="{W}" alt="Languages and tools" />

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
print("built:", "pinned repos" if d["pins"] else "fallback projects", "|", "stats" if d["repos"] else "no stats")
