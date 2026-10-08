"""Short first-sighting exchanges, separate from inspection and combat facts."""

from __future__ import annotations

from dataclasses import dataclass, field

JACK_LINES = {
    "normal": "うわあ……こんな湿地にまで出てきてる",
    "abnormal": "なんか……触手ついてるんだけど！？",
}
FUSE_REPLIES = (
    "気をつけて。泡で捕まえて、電撃よ。\nしっかり指示して頂戴ね",
    "大丈夫、大丈夫。いつも通りよ。\n補充が要るならスタンドを探してからね。",
)


def first_sight_lines(kind, seen):
    # Legacy sightings (including the old 「腕」 line) still count as completed occurrences.
    # Completed kinds are also the saved occurrence count. Cancellation never consumes it.
    reply = FUSE_REPLIES[min(len(set(seen) & JACK_LINES.keys()), 1)]
    return (("ジャック", JACK_LINES[kind]),) + tuple(
        ("ヒューズ", page) for page in reply.split("\n")
    )


FIRST_SIGHT_LINES = {kind: first_sight_lines(kind, set()) for kind in JACK_LINES}


@dataclass
class FirstSightConversation:
    kind: str
    target_id: str
    lines: tuple[tuple[str, str], ...]
    index: int = 0
    wait_release: bool = True


@dataclass
class FirstSightQueue:
    targets: dict[str, str] = field(default_factory=dict)
    cooldown: float = 0.0

    def observe(self, visible, seen, elapsed):
        self.cooldown = max(0.0, self.cooldown - elapsed)
        # A queued sighting must still have a visible subject when it is shown.
        self.targets = {kind: ident for kind, ident in visible.items() if kind not in seen}

    def begin(self, seen, safe, eligible=None):
        if not safe or self.cooldown > 0:
            return None
        for kind in ("abnormal", "normal"):
            if kind in self.targets and kind not in seen:
                if eligible is not None and self.targets[kind] not in eligible:
                    return None
                return FirstSightConversation(
                    kind, self.targets[kind], first_sight_lines(kind, seen)
                )
        return None

    def finish(self):
        self.cooldown = 4.0
