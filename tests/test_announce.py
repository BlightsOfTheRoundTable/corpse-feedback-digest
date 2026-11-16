from digest import announce

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Corpse Devlog</title>
<item><title>Devlog #4: Afflictions (v0.3.0)</title><link>https://crunchytuna.itch.io/corpse/devlog/9/devlog-4</link></item>
<item><title>Devlog #3: Tell Me How It Went</title><link>https://crunchytuna.itch.io/corpse/devlog/3/devlog-3</link></item>
<item><title>Elsewhere</title><link>https://example.com/devlog/1</link></item>
</channel></rss>"""


class Response:
    def __init__(self, content=b"", status=200):
        self.content = content
        self.status_code = status
        self.headers = {}


class Session:
    def __init__(self, feed):
        self.feed = feed
        self.posted = []

    def request(self, method, url, timeout=None, **kwargs):
        if method == "GET":
            return Response(self.feed)
        self.posted.append(kwargs["json"])
        return Response()


def test_parse_keeps_only_the_games_devlog_oldest_first():
    items = announce.parse(FEED)
    assert [i["link"] for i in items] == [
        "https://crunchytuna.itch.io/corpse/devlog/3/devlog-3",
        "https://crunchytuna.itch.io/corpse/devlog/9/devlog-4",
    ]


def test_first_run_notes_the_feed_and_posts_nothing(tmp_path):
    state = tmp_path / "announced.json"
    session = Session(FEED)
    assert announce.run("https://hook", state=state, session=session, pause=0) == 0
    assert session.posted == []
    assert len(announce.load(state)) == 2


def test_new_devlog_is_posted_once_without_pings(tmp_path):
    state = tmp_path / "announced.json"
    announce.save(state, ["https://crunchytuna.itch.io/corpse/devlog/3/devlog-3"])
    session = Session(FEED)
    assert announce.run("https://hook", state=state, session=session, pause=0) == 1
    body = session.posted[0]
    assert "Devlog #4: Afflictions (v0.3.0)" in body["content"]
    assert body["content"].endswith("https://crunchytuna.itch.io/corpse/devlog/9/devlog-4")
    assert body["allowed_mentions"] == {"parse": []}
    assert announce.run("https://hook", state=state, session=session, pause=0) == 0
    assert len(session.posted) == 1


def test_a_title_cant_ping(tmp_path):
    item = {"title": "@everyone **look**", "link": "https://crunchytuna.itch.io/corpse/devlog/1/x"}
    assert announce.message(item)["allowed_mentions"] == {"parse": []}
