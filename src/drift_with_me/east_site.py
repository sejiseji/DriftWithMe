"""Independent, session-only observations for the small eastern site."""

from __future__ import annotations

from dataclasses import dataclass, field

SITE_FACTS = {
    "jun_w2_canal_bank": "bank_unsafe",
    "jun_w2_shade": "shade_no_seat",
    "jun_w2_old_hatch": "hatch_present",
}
SITE_LABELS = {
    "jun_w2_canal_bank": "水路の岸",
    "jun_w2_shade": "木陰",
    "jun_w2_old_hatch": "古い点検口",
}
SITE_LINES = {
    "jun_w2_canal_bank": (
        ("ジャック", "向こうまで行けそう……いや、ここ崩れてるな"),
        ("ヒューズ", "無理しないの。戻ってこられなくなるわよ"),
    ),
    "jun_w2_shade": (
        ("ジャック", "ここ、涼しい。ちょっと休んでいかない？"),
        ("ヒューズ", "いいわよ。座れるものがあれば、もっとよかったけど"),
    ),
    "jun_w2_old_hatch": (
        ("ジャック", "これ、ふた？ 草に隠れてたんだ"),
        ("ヒューズ", "取っ手もあるわね。何につながってるのかしら"),
    ),
}


@dataclass
class EastSiteProgress:
    facts: set[str] = field(default_factory=set)
    positions: dict[str, int] = field(default_factory=dict)
    pending_completion: str | None = None

    def begin(self, target_id: str) -> tuple[tuple[tuple[str, str], ...], int]:
        self.pending_completion = None
        if SITE_FACTS[target_id] in self.facts:
            return (("ジャック", "ここは、さっき見たとおりだね。"),), 0
        lines = SITE_LINES[target_id]
        return lines, min(self.positions.get(target_id, 0), len(lines) - 1)

    def complete(self, target_id: str) -> bool:
        if target_id != self.pending_completion or target_id not in SITE_FACTS:
            return False
        self.facts.add(SITE_FACTS[target_id])
        self.positions.pop(target_id, None)
        self.pending_completion = None
        return True
