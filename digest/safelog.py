"""The only way this package writes to the log.

The repo is public, and so are its Actions logs. So nothing that came from a
player, a sheet, an API response or a secret is ever printed: only fixed
messages, counts, and the *type* of an error (never its message, which can
carry a URL with a key in it, a response body, or player text).
"""

from __future__ import annotations

import os


def info(message: str) -> None:
    """A fixed, content-free line (counts and names this code chose)."""
    print(message, flush=True)


def failure(where: str, error: BaseException) -> str:
    """Logs that `where` failed, by error type only. Returns the same short note."""
    note = f"{where}: failed ({type(error).__name__})"
    print(note, flush=True)
    return note


def mask(value: str | None) -> None:
    """Asks the Actions runner to hide `value` wherever it might appear later
    (for values made at run time, like an access token, that aren't stored
    secrets and so aren't masked automatically). Does nothing outside Actions."""
    if value and os.environ.get("GITHUB_ACTIONS") == "true":
        for line in str(value).splitlines():
            if line.strip():
                print(f"::add-mask::{line}", flush=True)
