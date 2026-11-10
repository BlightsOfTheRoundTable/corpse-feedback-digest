"""The digest as Discord messages (markdown, at most 2000 characters each).

Links are made here from each item's own URL, looked up by id. Words that
came from the model or a player are defanged first: no pings, no masked
links, no embeds (the webhook also turns mentions off, see deliver.py).
"""

from __future__ import annotations

import re
from datetime import datetime

from digest.items import Item

LIMIT = 1900  # Under Discord's 2000, with room to spare.
KIND_LABEL = {"bug": "BUG", "balance": "BALANCE", "confusion": "CONFUSING", "suggestion": "IDEA",
              "praise": "PRAISE", "other": "NOTE"}
SOURCE_NAME = {"discord": "Discord", "game": "in-game", "bug_form": "bug form", "youtube": "YouTube"}


def defang(text: str) -> str:
    """Model or player words, made safe to show: no @pings, no masked links
    or bare URLs that would unfurl, and no markdown headings or code fences."""
    text = str(text).replace("@", "@​")
    text = text.replace("](", "] (").replace("```", "'''")
    text = re.sub(r"https?://", lambda m: m.group(0).replace("://", ":​//"), text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    return text.strip()


def _refs(ids: list[str], items: dict[str, Item]) -> str:
    refs = []
    for item_id in ids:
        item = items.get(item_id)
        if item is None:
            continue
        refs.append(f"[{item_id}](<{item.url}>)" if item.url else item_id)
    return " ".join(refs)


def header(items: dict[str, Item], now: datetime, part: str = "") -> str:
    counts: dict[str, int] = {}
    for item in items.values():
        counts[item.source] = counts.get(item.source, 0) + 1
    where = ", ".join(f"{n} {SOURCE_NAME.get(source, source)}" for source, n in counts.items()) or "no new comments"
    return f"## Corpse feedback digest{part}\n{now:%a %d %b %Y, %H:%M} UTC · {where}"


def numbers(stats: dict | None) -> list[str]:
    """The run numbers, exactly as worked out from the sheet."""
    if not stats:
        return []
    lines = ["**Numbers** (new runs since last digest)"]
    if stats.get("runs"):
        results = ", ".join(f"{count} {result}" for result, count in stats.get("results", {}).items())
        minutes = stats.get("median_run_seconds")
        lines.append(f"• {stats['runs']} runs ({results})" + (f", median {minutes / 60:.0f} min" if minutes else ""))
        for village, row in stats.get("villages", {}).items():
            fell = row.get("median_segment_fallen")
            lines.append(f"• {defang(village)}: {row['runs']} runs, {row['won']} won, {row['boss']} reached the boss"
                         + (f", deaths around wave {fell:g}" if fell else ""))
    if stats.get("ratings"):
        lines.append("• Ratings: " + ", ".join(f"{defang(r)} {n}" for r, n in stats["ratings"].items()))
    if stats.get("most_taken_cards"):
        lines.append("• Cards taken most: " + ", ".join(f"{defang(c)} {r:.0%}" for c, r in stats["most_taken_cards"]))
        lines.append("• Cards skipped most: " + ", ".join(f"{defang(c)} {r:.0%}" for c, r in stats["most_skipped_cards"]))
    if stats.get("posture_share"):
        lines.append("• Time in posture: " + ", ".join(f"{defang(p)} {s:.0%}" for p, s in stats["posture_share"].items()))
    return lines


def render(digest: dict, items: dict[str, Item], stats: dict | None, now: datetime,
           notes: list[str], part: str = "") -> str:
    lines = [header(items, now, part), "", "> " + defang(digest.get("headline", "")).replace("\n", "\n> "), ""]
    lines += numbers(stats)
    for section in digest.get("sections", []):
        if not section.get("points"):
            continue
        lines += ["", f"**{defang(section.get('area', '?'))}**"]
        for point in section["points"]:
            label = KIND_LABEL.get(point.get("kind"), "NOTE")
            count = len(point.get("items", []))
            lines.append(f"• `{label}` {defang(point.get('summary', ''))}"
                         + (f" (×{count})" if count > 1 else "") + (f" {_refs(point['items'], items)}" if count else ""))
    if digest.get("reply_queue"):
        lines += ["", "**Worth a reply**"]
        for entry in digest["reply_queue"]:
            lines.append(f"• {_refs([entry['item']], items)} {defang(entry.get('why', ''))}")
    if digest.get("watch"):
        lines += ["", "**Watch**"]
        lines += [f"• {defang(line)}" for line in digest["watch"]]
    lines += _notes(notes)
    return "\n".join(lines)


def render_fallback(items: dict[str, Item], stats: dict | None, now: datetime, notes: list[str]) -> str:
    """When the summary couldn't be made: the new items themselves, briefly."""
    lines = [header(items, now), "", "_The summary couldn't be made this time; here's what came in._", ""]
    lines += numbers(stats)
    for item_id, item in items.items():
        snippet = defang(item.text.replace("\n", " "))
        snippet = snippet if len(snippet) <= 200 else snippet[:200] + "…"
        lines.append(f"• {_refs([item_id], items)} {defang(item.where)}, {defang(item.author)}: {snippet}")
    lines += _notes(notes)
    return "\n".join(lines)


def _notes(notes: list[str]) -> list[str]:
    return ["", "-# " + " · ".join(defang(note) for note in notes)] if notes else []


def split(text: str, limit: int = LIMIT) -> list[str]:
    """Discord-sized messages, broken between lines (a line that's too long on
    its own is cut)."""
    messages: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                messages.append(current)
                current = ""
            messages.append(line[:limit])
            line = line[limit:]
        if current and len(current) + 1 + len(line) > limit:
            messages.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current.strip():
        messages.append(current)
    return messages
