"""YouTube: new comments on the channel's recent videos, through the YouTube
Data API with an API key (restrict the key to the YouTube Data API v3 in the
Google Cloud console). Your own comments are skipped.

Each run looks at the RECENT_VIDEOS newest uploads, comment threads newest
first, stopping at the saved time. Replies come with their thread (up to the
five the API includes); a new reply on an old thread isn't picked up.
Quota: a few units a run, out of 10,000 a day.

Position: the time of the newest comment read.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from digest.http import get_json
from digest.items import Item

API = "https://www.googleapis.com/youtube/v3"
RECENT_VIDEOS = 15
PAGE = 100


class YouTubeSource:
    name = "YouTube"

    def __init__(self, api_key: str, channel_id: str, session: requests.Session | None = None):
        self.key = api_key
        self.channel_id = channel_id
        self.session = session or requests.Session()

    def _get(self, path: str, **params):
        params["key"] = self.key  # (In the query: HttpFailure never repeats the URL.)
        return get_json(self.session, f"{API}/{path}", params=params)

    def collect(self, state: dict, now: datetime, lookback_days: int) -> tuple[list[Item], dict]:
        since = _parse(state.get("youtube_after")) or now - timedelta(days=lookback_days)
        channel = self._get("channels", part="contentDetails", id=self.channel_id)
        uploads = channel["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        videos = self._get("playlistItems", part="snippet", playlistId=uploads, maxResults=RECENT_VIDEOS).get("items", [])
        items: list[Item] = []
        newest = since
        for video in videos:
            video_id = video["snippet"]["resourceId"]["videoId"]
            title = video["snippet"].get("title", "?")
            for comment in self._comments(video_id, since):
                when = _parse(comment["publishedAt"])
                newest = max(newest, when)
                if comment.get("authorChannelId", {}).get("value") == self.channel_id:
                    continue  # Yours.
                items.append(Item(
                    source="youtube",
                    where=f'YouTube: "{title}"',
                    author=comment.get("authorDisplayName", "?"),
                    text=comment.get("textOriginal", "").strip(),
                    url=f"https://www.youtube.com/watch?v={video_id}&lc={comment['id']}",
                    time=when.isoformat(),
                ))
        items = [item for item in items if item.text]
        items.sort(key=lambda item: item.time)
        return items, {"youtube_after": newest.isoformat()}

    def _comments(self, video_id: str, since: datetime) -> list[dict]:
        """Top-level comments and their included replies newer than `since`."""
        found: list[dict] = []
        token = None
        while True:
            params = {"part": "snippet,replies", "videoId": video_id, "order": "time", "maxResults": PAGE,
                      "textFormat": "plainText"}
            if token:
                params["pageToken"] = token
            try:
                page = self._get("commentThreads", **params)
            except Exception as error:
                if getattr(error, "status", 0) == 403:
                    return found  # Comments switched off on this video.
                raise
            older = False
            for thread in page.get("items", []):
                top = thread["snippet"]["topLevelComment"]
                replies = [dict(reply["snippet"], id=reply["id"]) for reply in thread.get("replies", {}).get("comments", [])]
                for comment in [dict(top["snippet"], id=top["id"]), *replies]:
                    if _parse(comment["publishedAt"]) > since:
                        found.append(comment)
                if _parse(thread["snippet"]["topLevelComment"]["snippet"]["publishedAt"]) <= since:
                    older = True
            token = page.get("nextPageToken")
            if older or not token:
                return found


def _parse(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
