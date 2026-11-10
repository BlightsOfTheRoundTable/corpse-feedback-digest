"""Runs one digest: collect what's new, summarise it, post it, save where each
source got to.

    python -m digest              # the real thing (what the workflow runs)
    python -m digest --dry-run    # writes the digest to out/digest.md instead
                                  # of posting it, and saves no progress

A source that fails is noted in the digest and keeps its old position (so its
items come next time); the others carry on. If nothing is new, nothing is
sent and Claude isn't called. If posting fails, no position moves, so the
next run sends it all again.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from digest import config as config_module
from digest import render, safelog, state as state_module
from digest.items import Item, number

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state" / "state.json"


@dataclass
class Collected:
    items: list[Item] = field(default_factory=list)
    stats: dict | None = None
    positions: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def collect(cfg: config_module.Config, state: dict, now: datetime, sources: dict[str, Callable] | None = None) -> Collected:
    """Every source that's set up; each failure noted, never fatal."""
    out = Collected()
    sources = sources if sources is not None else default_sources(cfg)
    for name, make in sources.items():
        try:
            items, stats, positions = make(state, now)
        except Exception as error:  # noqa: BLE001 - any source may fail; the rest go on.
            out.notes.append(safelog.failure(name, error))
            continue
        safelog.info(f"{name}: {len(items)} new")
        out.items += items
        if stats:
            out.stats = stats
        for key, value in positions.items():
            if key == "sheet_rows":
                out.positions.setdefault("sheet_rows", {}).update(value)
            else:
                out.positions[key] = value
    return out


def default_sources(cfg: config_module.Config) -> dict[str, Callable]:
    """The sources whose settings are present, each as state, now -> (items, stats, positions)."""
    sources: dict[str, Callable] = {}
    if cfg.discord_on:
        from digest.sources.discord import DiscordSource

        def discord(state, now):
            items, position = DiscordSource(cfg.discord_token, cfg.discord_guild_id, cfg.discord_channel_ids).collect(
                state, now, cfg.first_lookback_days)
            return items, None, position
        sources["Discord"] = discord
    if cfg.sheets and cfg.google_service_account_json:
        from digest.sources.sheets import SheetSource, access_token
        token: list[str] = []

        for sheet in cfg.sheets:
            def read(state, now, sheet=sheet):
                if not token:
                    token.append(access_token(cfg.google_service_account_json))
                items, stats, position = SheetSource(sheet.name, sheet.sheet_id, sheet.range, token[0]).collect(state)
                return items, stats, {"sheet_rows": position}
            sources[f"Sheet {sheet.name}"] = read
    if cfg.youtube_on:
        from digest.sources.youtube import YouTubeSource

        def youtube(state, now):
            items, position = YouTubeSource(cfg.youtube_api_key, cfg.youtube_channel_id).collect(
                state, now, cfg.first_lookback_days)
            return items, None, position
        sources["YouTube"] = youtube
    return sources


def run(cfg: config_module.Config, state_path: Path, now: datetime, *, sources: dict[str, Callable] | None = None,
        client=None, poster: Callable[[str], int] | None = None, dry_run: bool = False) -> int:
    """One digest. Returns the process exit code."""
    missing = cfg.problems()
    if missing and not dry_run:
        safelog.info("missing settings: " + ", ".join(missing))
        return 2
    state = state_module.load(state_path)
    got = collect(cfg, state, now, sources)
    new_state = dict(state, last_run=now.isoformat(timespec="seconds"))
    sheet_rows = dict(state.get("sheet_rows", {}))
    sheet_rows.update(got.positions.pop("sheet_rows", {}))
    new_state.update(got.positions, sheet_rows=sheet_rows)

    if not got.items and not got.stats and not got.notes:
        safelog.info("nothing new: no digest")
        if not dry_run:
            state_module.save(state_path, new_state)
        return 0

    by_id = number(got.items)
    messages = _digest(cfg, by_id, got, now, client)
    if dry_run:
        out = ROOT / "out" / "digest.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(messages, encoding="utf-8")
        safelog.info(f"dry run: digest written to out/digest.md ({len(by_id)} items), progress not saved")
        return 0
    try:
        sent = (poster or _post(cfg))(messages)
    except Exception as error:  # noqa: BLE001
        safelog.failure("posting the digest", error)
        return 1  # Nothing saved: the next run sends it all again.
    state_module.save(state_path, new_state)
    safelog.info(f"digest sent: {len(by_id)} items in {sent} message(s)")
    return 0


def _digest(cfg, by_id: dict[str, Item], got: Collected, now: datetime, client) -> str:
    from digest import summarize

    notes = list(got.notes)
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=cfg.anthropic_api_key, max_retries=3)
        parts = summarize.summarize(client, cfg.model, list(by_id.values()), got.stats, summarize.load_glossary(ROOT))
    except Exception as error:  # noqa: BLE001 - a failed summary still sends the raw items.
        notes.append(safelog.failure("summary", error))
        return render.render_fallback(by_id, got.stats, now, notes)
    texts = []
    for n, part in enumerate(parts):
        label = f" ({n + 1}/{len(parts)})" if len(parts) > 1 else ""
        texts.append(render.render(part, by_id, got.stats if n == 0 else None, now, notes if n == len(parts) - 1 else [], label))
    return "\n\n".join(texts)


def _post(cfg) -> Callable[[str], int]:
    from digest.deliver import post
    return lambda text: post(cfg.webhook_url, text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="digest")
    parser.add_argument("--dry-run", action="store_true", help="write out/digest.md instead of posting; save nothing")
    args = parser.parse_args(argv)
    config_module.load_dotenv(ROOT / ".env")
    cfg = config_module.load()
    try:
        return run(cfg, STATE_PATH, datetime.now(timezone.utc), dry_run=args.dry_run)
    except Exception as error:  # noqa: BLE001 - never let a traceback (and what it holds) reach the log.
        safelog.failure("digest", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
