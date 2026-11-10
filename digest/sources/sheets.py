"""The game's Google Form sheets, read with a service account that has view
access to each sheet (share the sheet with the account's email, as Viewer).

- run_reports: the in-game "Corpse run reports" form. Two kinds of row tied
  by a run id: stats rows (Stats is JSON) and feedback rows (Rating, Question,
  Answer). Feedback becomes items; the stats become numbers, worked out here,
  not by the model, so the digest's figures are exact.
- bug_reports: the "Report a bug" form; each new row becomes an item.

Position: how many rows each sheet had (forms only ever append). A first run
starts from the last FIRST_RUN_ROWS rows.
"""

from __future__ import annotations

import json
from collections import Counter
from statistics import median

import requests

from digest import safelog
from digest.http import get_json
from digest.items import Item

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
API = "https://sheets.googleapis.com/v4/spreadsheets"
FIRST_RUN_ROWS = 200
TEXT_LIMIT = 4000  # Per cell: a form answer is short; this only stops a runaway paste.


def access_token(service_account_json: str) -> str:
    """A short-lived read-only token for the service account."""
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    info = json.loads(service_account_json)
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    credentials.refresh(Request())
    safelog.mask(credentials.token)
    return credentials.token


class SheetSource:
    def __init__(self, name: str, sheet_id: str, range_: str, token: str, session: requests.Session | None = None):
        self.name = name
        self.sheet_id = sheet_id
        self.range = range_
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def rows(self) -> list[list[str]]:
        data = get_json(self.session, f"{API}/{self.sheet_id}/values/{requests.utils.quote(self.range, safe='')}")
        return data.get("values", [])

    def collect(self, state: dict) -> tuple[list[Item], dict | None, dict]:
        """(items, run stats or None, new position)."""
        values = self.rows()
        header = [cell.strip() for cell in values[0]] if values else []
        data = values[1:]
        seen = state.get("sheet_rows", {}).get(self.name)
        if seen is None:
            seen = max(0, len(data) - FIRST_RUN_ROWS)
        seen = min(seen, len(data))  # (Rows deleted by hand: start again from the end.)
        new = [dict(zip(header, row)) for row in data[seen:]]
        position = {self.name: len(data)}
        if self.name == "run_reports":
            items, stats = run_report_items(new), run_stats(new)
            return items, stats, position
        return bug_report_items(new, self.name), None, position


def _get(row: dict, name: str) -> str:
    for key, value in row.items():
        if key.strip().lower() == name:
            return str(value).strip()[:TEXT_LIMIT]
    return ""


def run_report_items(rows: list[dict]) -> list[Item]:
    """One item per run that got a rating or an answer: its last rating, and
    every answer (a run can send a rating row, then an answer row)."""
    runs: dict[str, dict] = {}
    for row in rows:
        rating, answer = _get(row, "rating"), _get(row, "answer")
        if not rating and not answer:
            continue
        run = _get(row, "run") or f"row{len(runs)}"
        entry = runs.setdefault(run, {"rating": "", "answers": [], "row": row})
        if rating:
            entry["rating"] = rating
        if answer and answer not in entry["answers"]:
            entry["answers"].append(answer)
        entry["row"] = row
    items = []
    for run, entry in runs.items():
        row = entry["row"]
        question = _get(row, "question")
        text = f"Rated the run: {entry['rating'] or '(no rating)'}."
        if entry["answers"]:
            text += f' Asked "{question}": ' + " / ".join(entry["answers"])
        items.append(Item(
            source="game",
            where=f"End-of-run ask, {_get(row, 'build') or '?'}",
            author="a player",
            text=text,
            time=_get(row, "timestamp"),
            extra={"village": _get(row, "village"), "result": _get(row, "result"), "reached": _get(row, "reached")},
        ))
    return items


def bug_report_items(rows: list[dict], name: str) -> list[Item]:
    items = []
    for row in rows:
        fields = [f"{key.strip()}: {str(value).strip()[:TEXT_LIMIT]}" for key, value in row.items()
                  if key.strip().lower() != "timestamp" and str(value).strip()]
        if fields:
            items.append(Item(source="bug_form", where="Report a bug form", author="a player",
                              text="\n".join(fields), time=_get(row, "timestamp")))
    return items


def run_stats(rows: list[dict]) -> dict | None:
    """Exact figures from the new runs' stats rows, and the ratings."""
    runs = []
    for row in rows:
        raw = _get(row, "stats")
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if isinstance(data, dict):
            data["_village"] = _get(row, "village")
            data["_build"] = _get(row, "build")
            runs.append(data)
    ratings = Counter(_get(row, "rating") for row in rows if _get(row, "rating") and not _get(row, "answer"))
    if not runs and not ratings:
        return None
    results = Counter(str(run.get("result", "?")) for run in runs)
    villages: dict[str, dict] = {}
    for run in runs:
        village = villages.setdefault(run["_village"] or "?", {"runs": 0, "won": 0, "boss": 0, "fell_at": []})
        village["runs"] += 1
        village["won"] += run.get("result") == "won"
        village["boss"] += bool(run.get("boss"))
        if run.get("result") == "fell" and isinstance(run.get("segment"), int):
            village["fell_at"].append(run["segment"])
    for village in villages.values():
        fell = village.pop("fell_at")
        village["median_segment_fallen"] = median(fell) if fell else None
    offered, taken = Counter(), Counter()
    posture, raised = Counter(), Counter()
    for run in runs:
        offered.update(_counts(run.get("offered")))
        taken.update(_counts(run.get("taken")))
        posture.update(_counts(run.get("posture_seconds")))
        raised.update(_counts(run.get("raised_by")))
    rates = {card: round(min(taken[card], offered[card]) / offered[card], 2) for card in offered if offered[card] >= 3}
    total_posture = sum(posture.values()) or 1
    seconds = [run["seconds"] for run in runs if isinstance(run.get("seconds"), (int, float))]
    return {
        "runs": len(runs),
        "results": dict(results),
        "ratings": dict(ratings),
        "builds": sorted({run["_build"] for run in runs if run["_build"]}),
        "villages": villages,
        "median_run_seconds": median(seconds) if seconds else None,
        "most_taken_cards": sorted(rates.items(), key=lambda pair: -pair[1])[:5],
        "most_skipped_cards": sorted(rates.items(), key=lambda pair: pair[1])[:5],
        "posture_share": {key: round(value / total_posture, 2) for key, value in posture.most_common()},
        "raised_by_type": dict(raised.most_common(8)),
        "input": dict(Counter(str(run.get("input", "?")) for run in runs)),
    }


def _counts(value) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int(count) for key, count in value.items() if isinstance(count, (int, float))}
