import json
from datetime import datetime, timezone

import pytest

from digest import render, safelog, state as state_module, summarize
from digest.__main__ import run
from digest.config import Config
from digest.http import HttpFailure
from digest.items import Item, number
from tests.fakes import FakeClient

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
SECRET = "sk-ant-THIS-MUST-NEVER-SHOW"


def _cfg():
    return Config(anthropic_api_key=SECRET, webhook_url="https://discord.com/api/webhooks/1/" + SECRET)


def _items():
    return [Item("discord", "#bugs", "Pat", "The Gleaner ate everything @everyone", "https://discord.com/channels/9/1/2"),
            Item("game", "End-of-run ask", "a player", "Rated the run: Frustrated.")]


def test_failures_log_the_error_type_only(capsys):
    safelog.failure("YouTube", ValueError(f"bad key {SECRET} in https://example.com/?key={SECRET}"))
    out = capsys.readouterr().out
    assert out == "YouTube: failed (ValueError)\n"


def test_a_failing_source_never_leaks_its_error_message(tmp_path, capsys):
    def broken(state, now):
        raise RuntimeError(f"401 for https://api/?key={SECRET}")
    sent = []
    code = run(_cfg(), tmp_path / "state.json", NOW, sources={"YouTube": broken},
               client=FakeClient(), poster=lambda text: sent.append(text) or 1)
    out = capsys.readouterr().out
    assert SECRET not in out and SECRET not in "".join(sent)
    assert code == 0 and "YouTube: failed (RuntimeError)" in sent[0]


def test_nothing_new_sends_nothing_and_skips_claude(tmp_path):
    client, sent = FakeClient(), []
    code = run(_cfg(), tmp_path / "state.json", NOW, sources={"Quiet": lambda s, n: ([], None, {"discord_after": "5"})},
               client=client, poster=lambda text: sent.append(text) or 1)
    assert code == 0 and sent == [] and client.calls == []
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved == {"discord_after": "5", "last_run": "2026-11-10T12:00:00+00:00"}


def test_a_failed_post_saves_no_progress(tmp_path):
    def refuse(text):
        raise HttpFailure(500)
    path = tmp_path / "state.json"
    state_module.save(path, {"discord_after": "1"})
    code = run(_cfg(), path, NOW, sources={"Discord": lambda s, n: (_items(), None, {"discord_after": "99"})},
               client=FakeClient(), poster=refuse)
    assert code == 1 and json.loads(path.read_text()) == {"discord_after": "1"}


def test_a_full_run_posts_and_saves(tmp_path):
    digest = {"headline": "The Gleaner is eating hordes.", "sections": [{"area": "Starvecrow", "points": [
        {"kind": "balance", "summary": "The Gleaner's bite feels unfair.", "items": ["D1", "G1", "Z9"]}]}],
        "reply_queue": [{"item": "D1", "why": "frustrated"}, {"item": "Z9", "why": "made up"}], "watch": []}
    client, sent = FakeClient(digest), []
    code = run(_cfg(), tmp_path / "state.json", NOW, sources={"Discord": lambda s, n: (_items(), None, {"discord_after": "99"})},
               client=client, poster=lambda text: sent.append(text) or 1)
    assert code == 0
    text = sent[0]
    assert "[D1](<https://discord.com/channels/9/1/2>)" in text and "Z9" not in text
    assert json.loads((tmp_path / "state.json").read_text())["discord_after"] == "99"
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    assert "<player_feedback>" in call["messages"][0]["content"]


def test_a_refused_summary_still_sends_the_items(tmp_path):
    sent = []
    run(_cfg(), tmp_path / "state.json", NOW, sources={"Discord": lambda s, n: (_items(), None, {})},
        client=FakeClient(stop_reason="refusal"), poster=lambda text: sent.append(text) or 1)
    assert "couldn't be made" in sent[0] and "summary: failed (SummaryFailed)" in sent[0]


def test_player_and_model_words_are_defanged():
    assert "@​everyone" in render.defang("hi @everyone")
    assert "](" not in render.defang("[click](https://evil.example)")
    assert "https://" not in render.defang("see https://evil.example")
    by_id = number(_items())
    text = render.render_fallback(by_id, None, NOW, [])
    assert "@everyone" not in text


def test_messages_fit_discords_limit():
    text = "\n".join(f"line {n} " + "x" * 150 for n in range(60)) + "\n" + "y" * 5000
    parts = render.split(text)
    assert all(len(part) <= render.LIMIT for part in parts)
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")


def test_state_file_keeps_positions_only(tmp_path):
    path = tmp_path / "state.json"
    state_module.save(path, {"discord_after": "123", "comment": "player text", "sheet_rows": {"run_reports": 4, "x y": 2},
                             "youtube_after": "2026-11-10T12:00:00+00:00", "last_run": "not a time"})
    assert json.loads(path.read_text()) == {"discord_after": "123", "sheet_rows": {"run_reports": 4},
                                            "youtube_after": "2026-11-10T12:00:00+00:00"}


def test_big_batches_are_split_not_cut():
    items = [Item("discord", "#x", "p", "z" * 40_000) for _ in range(9)]
    number(items)
    groups = summarize.chunks(items)
    assert len(groups) > 1 and sum(len(group) for group in groups) == 9


def test_config_never_shows_secrets():
    assert SECRET not in repr(_cfg()) and SECRET not in str(_cfg())


def test_missing_required_settings_stop_the_run(tmp_path, capsys):
    assert run(Config(), tmp_path / "state.json", NOW, sources={}) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out
