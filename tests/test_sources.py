import json
from datetime import datetime, timedelta, timezone

from digest.sources.discord import DiscordSource, snowflake_at
from digest.sources.sheets import run_report_items, run_stats, SheetSource
from digest.sources.youtube import YouTubeSource
from tests.fakes import FakeSession

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def _msg(moment, text, bot=False, kind=0, webhook=False):
    message = {"id": str(snowflake_at(moment)), "type": kind, "content": text,
               "author": {"username": "pat", "global_name": "Pat", "bot": bot}, "attachments": []}
    if webhook:
        message["webhook_id"] = "1"
    return message


def test_discord_reads_new_messages_and_threads_up_to_the_run_start():
    after = snowflake_at(NOW - timedelta(hours=12))
    old = _msg(NOW - timedelta(hours=13), "old news")
    new = _msg(NOW - timedelta(hours=1), "the tide is too fast")
    bot = _msg(NOW - timedelta(minutes=30), "beep", bot=True)
    hook = _msg(NOW - timedelta(minutes=20), "last digest", webhook=True)
    join = _msg(NOW - timedelta(minutes=10), "", kind=7)
    during = _msg(NOW + timedelta(seconds=5), "posted while the run was going")
    reply = _msg(NOW - timedelta(hours=2), "crash on the Gleaner")
    session = FakeSession([
        (r"/channels/100$", {"id": "100", "type": 0, "name": "general", "last_message_id": during["id"]}),
        (r"/channels/200$", {"id": "200", "type": 15, "name": "bug-reports"}),
        (r"/guilds/9/threads/active", {"threads": [
            {"id": "300", "parent_id": "200", "name": "Gleaner crash", "last_message_id": reply["id"]},
            {"id": "301", "parent_id": "999", "name": "elsewhere", "last_message_id": reply["id"]},
        ]}),
        (r"/threads/archived/public", {"threads": [], "has_more": False}),
        (r"/channels/100/messages", lambda params, _: [m for m in (during, join, hook, bot, new, old) if int(m["id"]) > int(params["after"])]),
        (r"/channels/300/messages", [reply]),
    ])
    items, position = DiscordSource("tok", "9", ["100", "200"], session).collect(
        {"discord_after": str(after)}, NOW, 7)
    texts = [item.text for item in items]
    assert texts == ["crash on the Gleaner", "the tide is too fast"]
    assert items[0].where == "#bug-reports > Gleaner crash"
    assert items[1].url == f"https://discord.com/channels/9/100/{new['id']}"
    assert position == {"discord_after": str(snowflake_at(NOW))}
    assert not any("/channels/301" in url for _, url, _ in session.calls), "threads outside the watched channels are skipped"


def test_discord_first_run_looks_back_the_set_number_of_days():
    session = FakeSession([
        (r"/channels/100$", {"id": "100", "type": 0, "name": "general", "last_message_id": "1"}),
        (r"/guilds/9/threads/active", {"threads": []}),
        (r"/threads/archived/public", {"threads": [], "has_more": False}),
    ])
    items, position = DiscordSource("tok", "9", ["100"], session).collect({}, NOW, 3)
    assert items == [] and position["discord_after"] == str(snowflake_at(NOW))


def _row(**cells):
    return {key.capitalize(): value for key, value in cells.items()}


def test_run_reports_merge_a_runs_rating_and_answer():
    rows = [
        _row(run="a1", build="v0.2.1", village="mires_end", result="fell", reached="segment 4 of 13", rating="Frustrated",
             question="Did the tide make Mire's End harder?", answer=""),
        _row(run="a1", build="v0.2.1", village="mires_end", result="fell", reached="segment 4 of 13", rating="Frustrated",
             question="Did the tide make Mire's End harder?", answer="Harder, it ate my horde"),
        _row(run="b2", rating="Loved it", question="q", answer=""),
        _row(run="c3", stats='{"result": "won"}'),
    ]
    items = run_report_items(rows)
    assert len(items) == 2
    assert items[0].text == 'Rated the run: Frustrated. Asked "Did the tide make Mire\'s End harder?": Harder, it ate my horde'
    assert items[0].extra == {"village": "mires_end", "result": "fell", "reached": "segment 4 of 13"}


def test_run_stats_are_exact():
    def stats_row(village, result, segment, offered, taken, posture):
        return _row(village=village, build="v0.2.1", stats=json.dumps({
            "result": result, "segment": segment, "boss": segment == 13, "seconds": 600,
            "offered": offered, "taken": taken, "posture_seconds": posture, "raised_by": {"skeleton": 10},
            "input": "keys"}))
    rows = [
        stats_row("mires_end", "fell", 4, {"wider_grave": 2, "long_reach": 1}, {"wider_grave": 1}, {"push": 30, "ball": 10}),
        stats_row("mires_end", "fell", 6, {"wider_grave": 1, "long_reach": 2}, {"wider_grave": 1}, {"push": 30}),
        stats_row("starvecrow", "won", 13, {"long_reach": 1}, {}, {"spread": 30}),
        _row(rating="Loved it", answer=""),
        _row(stats="not json"),
    ]
    stats = run_stats(rows)
    assert stats["runs"] == 3 and stats["results"] == {"fell": 2, "won": 1}
    assert stats["villages"]["mires_end"] == {"runs": 2, "won": 0, "boss": 0, "median_segment_fallen": 5}
    assert stats["villages"]["starvecrow"]["boss"] == 1
    assert dict(stats["most_taken_cards"]) == {"wider_grave": 0.67, "long_reach": 0.0}
    assert stats["posture_share"] == {"push": 0.6, "ball": 0.1, "spread": 0.3}
    assert stats["ratings"] == {"Loved it": 1}


def test_sheet_position_counts_rows_and_survives_deletions():
    header = ["Timestamp", "Details"]
    session = FakeSession([(r"/values/", {"values": [header, ["t1", "a"], ["t2", "b"], ["t3", "c"]]})])
    source = SheetSource("bug_reports", "sheet", "Form Responses 1", "tok", session)
    items, stats, position = source.collect({"sheet_rows": {"bug_reports": 1}})
    assert [item.text for item in items] == ["Details: b", "Details: c"] and stats is None
    assert position == {"bug_reports": 3}
    items, _, position = source.collect({"sheet_rows": {"bug_reports": 9}})
    assert items == [] and position == {"bug_reports": 3}


def test_youtube_skips_the_channels_own_comments_and_old_ones():
    since = NOW - timedelta(days=1)
    def comment(cid, author, when, text):
        return {"id": cid, "snippet": {"topLevelComment": {"id": cid, "snippet": {
            "authorDisplayName": author, "authorChannelId": {"value": author}, "textOriginal": text,
            "publishedAt": when.isoformat().replace("+00:00", "Z")}}}}
    session = FakeSession([
        (r"/channels", {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}),
        (r"/playlistItems", {"items": [{"snippet": {"title": "Devlog 2", "resourceId": {"videoId": "v1"}}}]}),
        (r"/commentThreads", {"items": [
            comment("c3", "viewer", NOW - timedelta(hours=1), "love the sirens"),
            comment("c2", "CHAN", NOW - timedelta(hours=2), "thanks all"),
            comment("c1", "viewer", NOW - timedelta(days=2), "old"),
        ]}),
    ])
    items, position = YouTubeSource("key", "CHAN", session).collect({"youtube_after": since.isoformat()}, NOW, 7)
    assert [item.text for item in items] == ["love the sirens"]
    assert items[0].url == "https://www.youtube.com/watch?v=v1&lc=c3"
    assert position["youtube_after"] == (NOW - timedelta(hours=1)).isoformat()
