"""Settings, all from the environment.

Secrets (GitHub: Settings > Secrets and variables > Actions > Secrets) are
encrypted, hidden from visitors, masked in logs and never given to forks.
Non-secret settings (ids, names) are Actions *variables*. Locally, a `.env`
file (git-ignored) can hold both; see .env.example.

A source whose settings are missing is simply off: the digest runs with the
rest. Nothing here is ever printed (see Config.__repr__).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SheetSettings:
    name: str  # run_reports or bug_reports: also its key in the state file
    sheet_id: str
    range: str


@dataclass
class Config:
    anthropic_api_key: str = ""
    webhook_url: str = ""
    discord_token: str = ""
    discord_guild_id: str = ""
    discord_channel_ids: list[str] = field(default_factory=list)
    google_service_account_json: str = ""
    sheets: list[SheetSettings] = field(default_factory=list)
    youtube_api_key: str = ""
    youtube_channel_id: str = ""
    first_lookback_days: int = 7
    model: str = "claude-opus-5-5"

    def __repr__(self) -> str:  # Never shows a secret, even by accident.
        return "Config(<hidden>)"

    __str__ = __repr__

    @property
    def discord_on(self) -> bool:
        return bool(self.discord_token and self.discord_guild_id and self.discord_channel_ids)

    @property
    def youtube_on(self) -> bool:
        return bool(self.youtube_api_key and self.youtube_channel_id)

    def problems(self) -> list[str]:
        """What's missing that the digest can't run without (names only)."""
        missing = []
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if not self.webhook_url:
            missing.append("DIGEST_WEBHOOK_URL")
        return missing


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _ids(name: str) -> list[str]:
    return [part.strip() for part in _env(name).split(",") if part.strip().isdigit()]


def load_dotenv(path: Path) -> None:
    """Reads KEY=value lines from a local .env into the environment (never in
    Actions, and never over a value that's already set)."""
    if os.environ.get("GITHUB_ACTIONS") == "true" or not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load() -> Config:
    sheets = []
    for name, prefix in (("run_reports", "RUN_REPORTS"), ("bug_reports", "BUG_REPORTS")):
        sheet_id = _env(f"{prefix}_SHEET_ID")
        if sheet_id:
            sheets.append(SheetSettings(name, sheet_id, _env(f"{prefix}_RANGE") or "Form Responses 1"))
    lookback = _env("FIRST_LOOKBACK_DAYS")
    return Config(
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        webhook_url=_env("DIGEST_WEBHOOK_URL"),
        discord_token=_env("DISCORD_BOT_TOKEN"),
        discord_guild_id=_env("DISCORD_GUILD_ID") if _env("DISCORD_GUILD_ID").isdigit() else "",
        discord_channel_ids=_ids("DISCORD_CHANNEL_IDS"),
        google_service_account_json=_env("GOOGLE_SERVICE_ACCOUNT_JSON"),
        sheets=sheets,
        youtube_api_key=_env("YOUTUBE_API_KEY"),
        youtube_channel_id=_env("YOUTUBE_CHANNEL_ID"),
        first_lookback_days=int(lookback) if lookback.isdigit() else 7,
        model=_env("DIGEST_MODEL") or "claude-opus-5-5",
    )
