# Privacy policy: Corpse Digest bot

The Corpse Digest bot helps the Corpse developers read player feedback.
This page explains what it reads, what it does with it, and what it keeps.

## What it reads

- Messages in the Corpse Discord server's feedback and bug-report channels,
  and nowhere else. It can't see DMs or other servers, and it never posts,
  replies or DMs anyone.
- Responses to the game's feedback and bug-report forms, and comments on the
  developers' YouTube videos.

## What it does with them

Twice a day, the new messages since the last run are sent to Anthropic's
Claude API to be summarised. The summary goes to a private channel that only
the Corpse developers can see. The summary may quote short parts of messages
and link back to them.

Anthropic processes this text under its commercial API terms, which don't
allow it to train models on the text.

## What it keeps

It doesn't store message text, usernames or anything else about you. The
only thing it saves is a bookmark: the id of the last message it read, row
counts for the form sheets, and the time of the last run, so the next run
starts where this one stopped. That bookmark is public, in this repository's
`state/state.json`.

The summaries stay in the developers' private Discord channel.

## Your choices

- If you don't want a message included, post it outside the feedback and
  bug-report channels.
- To ask about this, or to have a summary that mentions you removed, ask a
  moderator in the Corpse Discord server or open an issue on this repository.

## Changes

Changes to this policy are made in this repository, so its history shows
every change.
