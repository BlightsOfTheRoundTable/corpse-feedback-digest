"""Posts the digest to the private channel through a Discord webhook (no bot
needed to send). Pings are off whatever the text says, and link previews
are suppressed so the digest stays compact."""

from __future__ import annotations

import time

import requests

from digest.http import request
from digest.render import split

SUPPRESS_EMBEDS = 1 << 2
PAUSE = 1.0  # Between messages, under the webhook's rate limit.


def post(webhook_url: str, text: str, session: requests.Session | None = None) -> int:
    """Sends `text` as one or more messages. Returns how many. Raises
    HttpFailure (status only) if Discord refuses one."""
    session = session or requests.Session()
    messages = split(text)
    for n, content in enumerate(messages):
        if n:
            time.sleep(PAUSE)
        request(session, "POST", webhook_url, params={"wait": "true"}, json={
            "content": content,
            "allowed_mentions": {"parse": []},
            "flags": SUPPRESS_EMBEDS,
            "username": "Feedback digest",
        })
    return len(messages)
