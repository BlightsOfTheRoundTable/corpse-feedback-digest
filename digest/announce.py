"""Announces new itch.io devlog posts in the public Discord channel.

Run every half hour by .github/workflows/announce.yml: reads the game's devlog
RSS feed, and posts each item not announced before to a Discord webhook (the
title and the link; Discord unfurls the link into itch's own preview card).
No one is pinged.

The first run only learns what's already in the feed and posts nothing, so
old devlogs aren't announced all at once. What's been announced is kept in
state/announced.json as the posts' public links, nothing else.

Like the digest, it logs only counts and error types (see safelog.py): the
webhook URL is a secret, and lives only in the ANNOUNCE_WEBHOOK_URL secret.
"""

from __future__ import annotations

import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from digest import safelog
from digest.http import request

FEED_URL = "https://crunchytuna.itch.io/corpse/devlog.rss"
## Only links into the game's own devlog are announced (a feed that somehow
## names anything else is ignored).
LINK_PREFIX = "https://crunchytuna.itch.io/corpse/devlog/"
STATE = Path(__file__).resolve().parent.parent / "state" / "announced.json"
MAX_PER_RUN = 3  # A burst past this waits for the next run.
KEEP = 200  # Links remembered (far more than the feed ever lists).
TITLE_MAX = 200
PAUSE = 1.0


def parse(feed: bytes) -> list[dict]:
    """The feed's items, oldest first: {"title", "link"} each, links checked."""
    root = ET.fromstring(feed)
    items = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        title = " ".join((item.findtext("title") or "").split())
        if link.startswith(LINK_PREFIX) and title and not any(c in link for c in "<>\"' "):
            items.append({"title": title[:TITLE_MAX], "link": link})
    items.reverse()  # (RSS lists the newest first.)
    return items


def message(item: dict) -> dict:
    """The webhook's message for one devlog. No pings, whatever the title says."""
    title = item["title"].replace("*", "").replace("_", "\\_").replace("`", "")
    return {
        "content": f"**New devlog: {title}**\n{item['link']}",
        "allowed_mentions": {"parse": []},
        "username": "Corpse devlog",
    }


def load(path: Path) -> list[str] | None:
    """The links announced so far, or None before the first run."""
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return [str(link) for link in data.get("announced", []) if isinstance(link, str)]


def save(path: Path, announced: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"announced": announced[-KEEP:]}, indent=2) + "\n", encoding="utf-8")


def run(webhook_url: str, feed_url: str = FEED_URL, state: Path = STATE,
        session: requests.Session | None = None, pause: float = PAUSE) -> int:
    """Announces what's new. Returns how many were posted."""
    session = session or requests.Session()
    items = parse(request(session, "GET", feed_url).content)
    announced = load(state)
    if announced is None:  # The first run: learn the feed, post nothing.
        save(state, [item["link"] for item in items])
        safelog.info(f"announce: first run, {len(items)} existing devlogs noted, none posted")
        return 0
    fresh = [item for item in items if item["link"] not in announced][:MAX_PER_RUN]
    for n, item in enumerate(fresh):
        if n:
            time.sleep(pause)
        request(session, "POST", webhook_url, params={"wait": "true"}, json=message(item))
        announced.append(item["link"])
        save(state, announced)  # After each, so a failure later doesn't repeat it.
    safelog.info(f"announce: {len(items)} in the feed, {len(fresh)} posted")
    return len(fresh)


def main() -> int:
    webhook_url = os.environ.get("ANNOUNCE_WEBHOOK_URL", "")
    if not webhook_url:  # Not set up yet: skip quietly rather than fail every half hour.
        safelog.info("announce: ANNOUNCE_WEBHOOK_URL is not set; skipped")
        return 0
    try:
        run(webhook_url, os.environ.get("DEVLOG_FEED_URL") or FEED_URL)
    except Exception as error:  # noqa: BLE001 (logged by type only)
        safelog.failure("announce", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
