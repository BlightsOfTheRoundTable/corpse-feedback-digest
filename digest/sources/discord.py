"""Discord: new messages in the feedback channels (text channels, and forum
channels' posts and replies), read through the REST API with a bot token.

The bot needs View Channel and Read Message History on those channels, and the
Message Content intent switched on in the Developer Portal (without it,
message text comes back empty). It never posts: the digest goes out through a
webhook.

Position: one message id. Discord ids are timestamps in disguise, so "after
this id" means "after this moment" in every channel at once. Each run reads
up to the moment it started and saves that moment, so nothing posted during a
run is missed or read twice.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from digest.http import get_json
from digest.items import Item

API = "https://discord.com/api/v10"
EPOCH_MS = 1420070400000  # Discord's epoch (2015-01-01).
TEXT_TYPES = {0, 5}  # Text, announcement.
FORUM_TYPES = {15, 16}  # Forum, media.
THREAD_TYPES = {10, 11, 12}
USER_MESSAGE_TYPES = {0, 19}  # A message, a reply (not joins, pins, boosts...).
PAGE = 100


def snowflake_at(moment: datetime) -> int:
    return (int(moment.timestamp() * 1000) - EPOCH_MS) << 22


def time_of(snowflake: int) -> datetime:
    return datetime.fromtimestamp(((snowflake >> 22) + EPOCH_MS) / 1000, tz=timezone.utc)


class DiscordSource:
    name = "Discord"

    def __init__(self, token: str, guild_id: str, channel_ids: list[str], session: requests.Session | None = None):
        self.guild_id = guild_id
        self.channel_ids = channel_ids
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bot {token}", "User-Agent": "corpse-feedback-digest (1.0)"})

    def _get(self, path: str, **params):
        return get_json(self.session, f"{API}{path}", params=params or None)

    def collect(self, state: dict, now: datetime, lookback_days: int) -> tuple[list[Item], dict]:
        """New messages since state["discord_after"] (or the last few days, on a
        first run), and the position to save."""
        upto = snowflake_at(now)
        after = int(state.get("discord_after") or snowflake_at(now - timedelta(days=lookback_days)))
        channels = {cid: self._get(f"/channels/{cid}") for cid in self.channel_ids}
        targets: list[tuple[str, str]] = []  # (channel or thread id, label)
        for cid, channel in channels.items():
            if channel.get("type") in TEXT_TYPES and _newer(channel.get("last_message_id"), after):
                targets.append((cid, f"#{channel.get('name', '?')}"))
        for thread in self._threads(channels, after):
            parent = channels.get(str(thread.get("parent_id")), {})
            targets.append((str(thread["id"]), f"#{parent.get('name', '?')} > {thread.get('name', '?')}"))
        items: list[Item] = []
        for channel_id, label in targets:
            for message in self._messages(channel_id, after, upto):
                item = self._item(message, channel_id, label)
                if item:
                    items.append(item)
        items.sort(key=lambda item: item.time)
        return items, {"discord_after": str(upto)}

    def _threads(self, channels: dict, after: int) -> list[dict]:
        """Threads in the watched channels with messages newer than `after`:
        the active ones, and ones archived since then (a thread can go quiet and
        auto-archive between two runs)."""
        found: dict[str, dict] = {}
        active = self._get(f"/guilds/{self.guild_id}/threads/active").get("threads", [])
        for thread in active:
            if str(thread.get("parent_id")) in channels and _newer(thread.get("last_message_id"), after):
                found[str(thread["id"])] = thread
        since = time_of(after)
        for cid, channel in channels.items():
            if channel.get("type") not in FORUM_TYPES | TEXT_TYPES:
                continue
            before = None
            while True:
                params = {"limit": 50}
                if before:
                    params["before"] = before
                page = self._get(f"/channels/{cid}/threads/archived/public", **params)
                threads = page.get("threads", [])
                done = False
                for thread in threads:
                    archived = thread.get("thread_metadata", {}).get("archive_timestamp", "")
                    if archived and datetime.fromisoformat(archived) < since:
                        done = True  # Newest first: the rest were archived earlier still.
                        break
                    if _newer(thread.get("last_message_id"), after):
                        found[str(thread["id"])] = thread
                if done or not page.get("has_more") or not threads:
                    break
                before = threads[-1].get("thread_metadata", {}).get("archive_timestamp")
        return list(found.values())

    def _messages(self, channel_id: str, after: int, upto: int) -> list[dict]:
        messages: list[dict] = []
        cursor = after
        while True:
            page = self._get(f"/channels/{channel_id}/messages", after=str(cursor), limit=PAGE)
            if not page:
                break
            page.sort(key=lambda message: int(message["id"]))
            messages.extend(message for message in page if int(message["id"]) <= upto)
            cursor = int(page[-1]["id"])
            if len(page) < PAGE or cursor > upto:
                break
        return messages

    def _item(self, message: dict, channel_id: str, label: str) -> Item | None:
        author = message.get("author", {})
        if author.get("bot") or message.get("webhook_id") or message.get("type", 0) not in USER_MESSAGE_TYPES:
            return None  # Bots, webhooks (the digest itself) and system notices.
        text = message.get("content", "").strip()
        attachments = [a.get("filename", "file") for a in message.get("attachments", [])]
        if attachments:
            text = (text + "\n" if text else "") + "[attached: " + ", ".join(attachments) + "]"
        if not text:
            return None
        return Item(
            source="discord",
            where=label,
            author=author.get("global_name") or author.get("username", "?"),
            text=text,
            url=f"https://discord.com/channels/{self.guild_id}/{channel_id}/{message['id']}",
            time=time_of(int(message["id"])).isoformat(),
        )


def _newer(snowflake, after: int) -> bool:
    try:
        return int(snowflake) > after
    except (TypeError, ValueError):
        return False
