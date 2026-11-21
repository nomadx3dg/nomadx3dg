"""Shared state and rules for the pixel wall (used by paint.py and build.py)."""
import json
from pathlib import Path

W, H = 32, 16
COOLDOWN = 300  # seconds between paints per person
PALETTE = [("Bone", "#efe9dc"), ("Ink", "#1b1a17"), ("Crimson", "#e8203a"), ("Orange", "#ff8a1f"),
           ("Yellow", "#f5d742"), ("Green", "#3ecf6e"), ("Blue", "#3a7bff"), ("Violet", "#9b5cff")]
NAMES = {name: i for i, (name, _) in enumerate(PALETTE)}
PATH = Path(__file__).parent / "data" / "canvas.json"


def seed():
    """A small crimson N in the middle, so the wall doesn't start empty."""
    px = {}
    for y in range(5, 12):
        px[f"14,{y}"] = 2
        px[f"18,{y}"] = 2
        px[f"{14 + round((y - 5) * 4 / 6)},{y}"] = 2
    return {"pixels": px, "paints": 0, "last": None, "cooldown": {}}


def load():
    try:
        return json.loads(PATH.read_text())
    except Exception:
        return seed()


def save(state):
    PATH.parent.mkdir(exist_ok=True)
    PATH.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


def paint(state, x, y, color, login, now):
    state["pixels"][f"{x},{y}"] = NAMES[color]
    state["paints"] += 1
    state["last"] = {"user": login, "x": x, "y": y, "color": color, "at": now.isoformat(timespec="seconds")}
    state["cooldown"][login] = now.isoformat(timespec="seconds")
