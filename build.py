#!/usr/bin/env python3
"""Builds README.md from profile.json. Standard library only.

Live music: YouTube Music has no public now-playing API, so scrobble it to
Last.fm (Web Scrobbler or Pano Scrobbler) and set LASTFM_API_KEY. Without the
key, the fallback text from profile.json is used.
"""
import json, os, urllib.parse, urllib.request
from pathlib import Path

root = Path(__file__).parent
p = json.loads((root / "profile.json").read_text())
gh = p["github_username"]


def badge(name, logo):
    icon = f"&logo={logo}&logoColor=ffffff" if logo else ""
    return (f'<img src="https://img.shields.io/badge/{urllib.parse.quote(name)}-000000'
            f'?style=flat-square{icon}&labelColor=000000&color=000000" alt="{name}" />')


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
        live = t.get("@attr", {}).get("nowplaying") == "true"
        label = "now playing" if live else "last played"
        return f'{label}   {t["artist"]["#text"]} - {t["name"]}', t.get("url")
    except Exception:
        return m["fallback"], None


def pinned_repos(limit):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    query = ("query($u:String!){user(login:$u){pinnedItems(first:6,types:REPOSITORY)"
             "{nodes{... on Repository{name description}}}}}")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"u": gh}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            nodes = json.load(r)["data"]["user"]["pinnedItems"]["nodes"]
        repos = [{"repo": n["name"], "description": n["description"] or "no description yet"}
                 for n in nodes if n]
        return repos[:limit] or None
    except Exception:
        return None


def img(slug, alt):
    return f'<img src="assets/h-{slug}.svg" width="100%" alt="{alt}" />'


s = p["status"]
pins, lines = [], []
src = p.get("projects_source", {})
projects = None
if src.get("mode") == "pinned":
    projects = pinned_repos(src.get("max", 3))
projects = projects or p["projects_fallback"]
for pr in projects:
    url = f'https://github.com/{gh}/{pr["repo"]}'
    pins.append(f'<a href="{url}"><img src="https://github-readme-stats.vercel.app/api/pin/?username={gh}'
                f'&repo={pr["repo"]}&hide_border=true&bg_color=000000&title_color=ffffff&text_color=bbbbbb'
                f'&icon_color=ffffff" alt="{pr["repo"]}" /></a>')
    lines.append(f'{pr["repo"].lower():<16}{pr["description"]}')

track, track_url = now_playing()
track_md = f"```\n{track}\n```"
if track_url:
    track_md += f"\n[Open on Last.fm]({track_url})"

stats = ("hide_border=true&bg_color=000000&title_color=ffffff&text_color=bbbbbb&icon_color=ffffff&hide_title=true")
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

```
{chr(10).join(lines)}
```

{img('stack', 'Stack')}

{chr(10).join(badge(*x) for x in p['skills']['languages'])}

{chr(10).join(badge(*x) for x in p['skills']['tools'])}

{img('art', 'Art')}

<p align="center">
  <img src="assets/nomad-logo.jpg" width="48%" alt="NOMAD lettering" />
  <img src="assets/nomad-ascii.jpg" width="48%" alt="ASCII study" />
</p>

{img('listening', 'Listening')}

{track_md}

<sub>via {p['music']['service']}</sub>

{img('github', 'GitHub')}

<img src="https://github-readme-stats.vercel.app/api?username={gh}&show_icons=true&{stats}" alt="GitHub stats" />
<img src="https://github-readme-stats.vercel.app/api/top-langs/?username={gh}&layout=compact&hide_border=true&bg_color=000000&title_color=ffffff&text_color=bbbbbb&hide_title=true" alt="Top languages" />

{img('contributing', 'Contributing')}

{p['contributing']}

{img('contact', 'Contact')}

{links}

<img src="assets/divider.svg" width="100%" alt="" />

<div align="center"><sub>{p['footer']}</sub></div>
"""
(root / "README.md").write_text(readme)
print("README.md written")
