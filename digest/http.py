"""HTTP for the sources and the webhook: retries rate limits and server errors,
and fails with an error that holds only the status code (never the URL, which
can carry a key, or the body, which can carry player text)."""

from __future__ import annotations

import time

import requests

TIMEOUT = 30
RETRIES = 3


class HttpFailure(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


def request(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    for attempt in range(RETRIES + 1):
        try:
            response = session.request(method, url, timeout=TIMEOUT, **kwargs)
        except requests.RequestException as error:
            if attempt == RETRIES:
                raise HttpFailure(0) from None  # (The original names the URL: dropped.)
            time.sleep(2 ** attempt)
            continue
        if response.status_code == 429 and attempt < RETRIES:
            time.sleep(min(_retry_after(response), 30.0))
            continue
        if response.status_code >= 500 and attempt < RETRIES:
            time.sleep(2 ** attempt)
            continue
        if response.status_code >= 400:
            raise HttpFailure(response.status_code)
        return response
    raise HttpFailure(0)


def get_json(session: requests.Session, url: str, **kwargs):
    return request(session, "GET", url, **kwargs).json()


def _retry_after(response: requests.Response) -> float:
    try:
        return float(response.headers.get("retry-after") or response.json().get("retry_after", 1.0))
    except (ValueError, AttributeError):
        return 1.0
