"""One thing a player said, from any source."""

from __future__ import annotations

from dataclasses import dataclass, field

# Short id prefixes, by source (D3, G1, ...): Claude refers to items by these,
# and the digest turns them back into links. Claude never writes a link itself.
PREFIX = {"discord": "D", "game": "G", "bug_form": "B", "youtube": "Y"}


@dataclass
class Item:
    source: str  # discord, game, bug_form, youtube
    where: str  # channel and thread, video title, form name
    author: str
    text: str
    url: str = ""
    time: str = ""  # ISO 8601, UTC
    id: str = ""
    extra: dict = field(default_factory=dict)

    def for_model(self) -> dict:
        """What Claude sees of it."""
        data = {"id": self.id, "source": self.source, "where": self.where, "author": self.author,
                "time": self.time, "text": self.text}
        data.update(self.extra)
        return data


def number(items: list[Item]) -> dict[str, Item]:
    """Gives each item its short id, in order, and returns them by id."""
    counts: dict[str, int] = {}
    by_id: dict[str, Item] = {}
    for item in items:
        prefix = PREFIX.get(item.source, "X")
        counts[prefix] = counts.get(prefix, 0) + 1
        item.id = f"{prefix}{counts[prefix]}"
        by_id[item.id] = item
    return by_id
