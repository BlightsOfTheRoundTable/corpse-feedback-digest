# Keeping a public repo's secrets secret

This repo is public (public repos get free Actions minutes), and it holds
keys to Discord, Google, YouTube and the Anthropic API. These are the rules
it follows, and what to keep doing.

## Where secrets live

- **Only in GitHub Actions secrets**, or a local `.env` that git ignores.
  Never in code, config, commits, issues or workflow files.
- Actions secrets are encrypted, never shown to visitors, masked in logs, and
  never given to workflows from forks.
- Only the one step that runs the digest receives them. The step that
  commits progress gets just the workflow's own short-lived token.

## What the logs show

Actions logs on a public repo are public. So the code prints only fixed
messages, counts, and the *type* of an error, never its message (an error
message can hold a URL with a key in it, an API response, or player text).
All logging goes through `digest/safelog.py`. A test feeds a secret into a
failing source and checks it never appears in the output.

Tokens made at run time (the Google access token) are masked with
`::add-mask::` as soon as they exist.

## What gets committed

`state/state.json` is public too. It holds positions only (a Discord message
id, sheet row counts, a timestamp); `digest/state.py` drops anything else on
save, so comment text can never end up there.

## The workflow

- Triggers: the schedule and a manual run only. Never `pull_request_target`,
  which would run untrusted code with secrets.
- It runs only in this repository (`if: github.repository == ...`).
- Default permissions are read-only; the digest job can write contents only
  to commit `state/state.json`.
- Third-party actions are pinned to full commit SHAs, and Python packages
  are installed with `--require-hashes`. Dependabot proposes updates; review
  them before merging, since they change what runs alongside the secrets.

## Untrusted input

Player messages go to Claude as data inside tags, with an instruction that
they're material to summarise, not instructions to follow. Claude has no
tools, so it can't act on anything. The digest's links are built from the
items' own URLs by id, never from the model's words; pings are disabled on
the webhook, and links in the model's text are defanged.

## Turn these on in the repo settings

- Settings > Code security: **Secret scanning** and **Push protection**
  (free for public repos), so a secret pushed by mistake is blocked or flagged.
- Settings > Actions > General: choose the strictest approval setting for
  workflows from fork pull requests (approval required for every outside
  contributor), and keep the default workflow permissions **read-only**.
- Settings > Rules > Rulesets: a ruleset on `main` that blocks force pushes
  and deletions. Don't require pull requests on `main`: the digest commits
  its progress file there directly, and that rule would stop it.

## If a secret leaks

Revoke it at its source first (Discord: Reset Token; Google: delete the key;
Anthropic: delete the key; the webhook: delete and recreate it), then
replace the GitHub secret. Deleting a commit doesn't un-leak a secret: the
old value must stop working.
