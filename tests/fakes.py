"""Stand-ins for HTTP and the Anthropic client, so tests never touch the network."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace


class FakeResponse:
    def __init__(self, status: int, body):
        self.status_code = status
        self._body = body
        self.headers = {}

    def json(self):
        return self._body


class FakeSession:
    """Answers GETs from a table of (regex on URL path, params predicate) -> body,
    and records every request."""

    def __init__(self, routes: list[tuple[str, object]]):
        self.routes = routes
        self.headers: dict = {}
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, url, timeout=None, params=None, json=None, **_):
        self.calls.append((method, url, params or {}))
        for pattern, body in self.routes:
            if re.search(pattern, url):
                value = body(params or {}, json) if callable(body) else body
                if isinstance(value, FakeResponse):
                    return value
                return FakeResponse(200, value)
        return FakeResponse(404, {"message": "no route"})


class FakeClient:
    """messages.create returns a canned digest as JSON text, or a set stop reason."""

    def __init__(self, digest: dict | None = None, stop_reason: str = "end_turn"):
        self.digest = digest or {"headline": "h", "sections": [], "reply_queue": [], "watch": []}
        self.stop_reason = stop_reason
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=json.dumps(self.digest))],
        )
