"""Where each source got to, kept in state/state.json and committed back to the
repo after every run (which also keeps the scheduled workflow from being
paused for inactivity).

The repo is public, so the file holds only positions: a Discord message id
(a timestamp in disguise), sheet row counts, a timestamp, and when it last ran.
Anything else is dropped on save, so no comment text can end up there.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# The keys the file may hold, and what each value must look like.
_ID = re.compile(r"^\d{1,25}$")
_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
_SHEET_NAME = re.compile(r"^[a-z_]{1,32}$")


def clean(state: dict) -> dict:
    """Only the allowed keys, with values of the allowed shape."""
    out: dict = {}
    after = state.get("discord_after")
    if isinstance(after, str) and _ID.match(after):
        out["discord_after"] = after
    for key in ("youtube_after", "last_run"):
        value = state.get(key)
        if isinstance(value, str) and _TIME.match(value):
            out[key] = value
    sheets = state.get("sheet_rows")
    if isinstance(sheets, dict):
        rows = {name: count for name, count in sheets.items()
                if isinstance(name, str) and _SHEET_NAME.match(name) and isinstance(count, int) and 0 <= count < 10**9}
        if rows:
            out["sheet_rows"] = rows
    return out


def load(path: Path) -> dict:
    try:
        return clean(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(state), indent=2, sort_keys=True) + "\n", encoding="utf-8")
