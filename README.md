# Corpse feedback digest

Twice a day, a GitHub Actions job collects what players said about
Corpse since the last run, has Claude
group and triage it, and posts one digest to a private Discord channel. Nothing
needs checking by hand.

It reads:

- **Discord:** new messages in the feedback and bug-report channels (forum
  posts and their replies, or text channels).
- **The game's run reports sheet:** the end-of-run rating and this build's
  question, plus exact numbers from the anonymous run stats (results by
  village, where runs end, which cards get taken or skipped, time in each
  posture).
- **The bug report form's sheet.**
- **YouTube:** new comments on the channel's recent videos.

It's read-only: it never replies to players or posts anywhere public. The
digest goes to one channel through a webhook.

## What a digest looks like

A headline, the run numbers, then points grouped by village or system
(`BUG`, `BALANCE`, `CONFUSING`, `IDEA`, `PRAISE`), each linking to the
messages it came from; then the items worth a reply, and trends to watch.
If nothing is new, nothing is posted and Claude isn't called. If a source
fails, the digest says which, and that source catches up next run.

## Setup

Each source is optional: leave its settings out and it's skipped. Only the
Anthropic key and the webhook are required.

### 1. The digest channel's webhook (required)

In Discord, the private channel's settings (for example #mod-log) >
Integrations > Webhooks > New Webhook. Copy its URL into the
`DIGEST_WEBHOOK_URL` secret.

### 2. Anthropic API key (required)

From console.anthropic.com > API keys. Put it in `ANTHROPIC_API_KEY`. Set a
monthly spend limit on the workspace too: with two runs a day and
skipping empty runs, the cost should be small, and the limit makes sure it stays that way.

### 3. Discord bot (to read the feedback channels)

1. discord.com/developers/applications > New Application > Bot.
2. Under Privileged Gateway Intents, switch on **Message Content Intent**
   (without it, message text comes back empty).
3. Reset Token, and put the token in the `DISCORD_BOT_TOKEN` secret.
4. OAuth2 > URL Generator: scope `bot`, permissions **View Channels** and
   **Read Message History** only. Open the URL to add it to the server.
5. In the server, make sure the bot's role can see the feedback channels.
6. With Developer Mode on (User Settings > Advanced), right-click the server
   and the channels to copy their ids into the `DISCORD_GUILD_ID` and
   `DISCORD_CHANNEL_IDS` variables (channel ids comma-separated).

### 4. Google Sheets (the game's two forms)

1. In Google Cloud console, create a project, enable the **Google Sheets
   API**, then IAM & Admin > Service Accounts > Create. It needs no roles.
2. Keys > Add key > JSON. Put the whole file's contents in the
   `GOOGLE_SERVICE_ACCOUNT_JSON` secret, then delete the downloaded file.
3. Share each response sheet with the service account's email as **Viewer**.
4. Put each sheet's id (the long part of its URL) in `RUN_REPORTS_SHEET_ID`
   and `BUG_REPORTS_SHEET_ID`. If the tab isn't called "Form Responses 1",
   set `RUN_REPORTS_RANGE` / `BUG_REPORTS_RANGE` to its name.

### 5. YouTube

In the same Google Cloud project, enable the **YouTube Data API v3**, then
APIs & Services > Credentials > Create credentials > API key. Restrict it to
the YouTube Data API v3. Put it in `YOUTUBE_API_KEY`, and the channel's id
(youtube.com/account_advanced) in the `YOUTUBE_CHANNEL_ID` variable.

### 6. In GitHub

Settings > Secrets and variables > Actions.

| Secrets | Variables |
|---|---|
| `ANTHROPIC_API_KEY` | `DISCORD_GUILD_ID` |
| `DIGEST_WEBHOOK_URL` | `DISCORD_CHANNEL_IDS` |
| `DISCORD_BOT_TOKEN` | `RUN_REPORTS_SHEET_ID`, `RUN_REPORTS_RANGE` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | `BUG_REPORTS_SHEET_ID`, `BUG_REPORTS_RANGE` |
| `YOUTUBE_API_KEY` | `YOUTUBE_CHANNEL_ID` |
| | `FIRST_LOOKBACK_DAYS` (default 7: how far back the very first run reads) |

Then Actions > Feedback digest > Run workflow to try it.

## Running it on your own machine

```bash
python -m venv .venv
.venv/Scripts/python -m pip install --require-hashes -r requirements-dev.txt
cp .env.example .env   # and fill it in
.venv/Scripts/python -m digest --dry-run   # writes out/digest.md, posts nothing, saves nothing
.venv/Scripts/python -m pytest -q
```

## Changing things

- **Schedule:** the two `cron` lines in `.github/workflows/digest.yml` (UTC).
- **What Claude is told:** `SYSTEM` in `digest/summarize.py`, and the
  glossary in `context/game.md` (keep it current as villages and systems change).
- **Dependencies:** edit `requirements.in`, then
  `uv pip compile requirements.in --generate-hashes --python-version 3.12 --python-platform x86_64-unknown-linux-gnu -o requirements.txt`
  (and the same for `requirements-dev.in`).

## Not yet

- **Reddit** comments on your own posts (Reddit's API now needs an approved
  app; a read-only script app is the plan).
- **itch.io** comments (no API; it would parse the public page, which breaks
  whenever itch changes its layout).
- Later and optional: suggested replies for you to approve, GitHub issues for
  confirmed bugs. It stays read-only until then.

See [SECURITY.md](SECURITY.md) for how secrets are kept out of this public repo.
