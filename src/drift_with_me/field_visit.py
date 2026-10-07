"""Case-local observations and short conversations for the north-shallow visit."""

from __future__ import annotations

from dataclasses import dataclass, field

OBSERVATIONS = {
    "tap_stopped": ("supply_stopped", "止まった蛇口では、水が出ていませんでした。"),
    "maintenance_unit": (
        "robot_measurement",
        "測定ロボと、水の入った測定用の容器を確認しました。",
    ),
    "observation_post": ("post_present", "観測柱が立っているのを確認しました。"),
}
ANOMALY_ID = "urchin_abnormal_04"


@dataclass
class FieldProgress:
    observations: dict[str, str] = field(default_factory=dict)
    conversations_completed: set[str] = field(default_factory=set)
    conversation_positions: dict[str, int] = field(default_factory=dict)
    enemy_ids: set[str] = field(default_factory=set)
    dealt_target_ids: set[str] = field(default_factory=set)
    interrupted: bool = False
    event_floor: int = 0
    last_event_id: int = 0

    @property
    def can_report(self) -> bool:
        return bool(
            self.observations or self.enemy_ids or self.dealt_target_ids or self.interrupted
        )

    def observe(self, target_id: str) -> None:
        if target_id in OBSERVATIONS:
            key, text = OBSERVATIONS[target_id]
            self.observations[key] = text
        elif target_id == ANOMALY_ID:
            self.enemy_ids.add(target_id)

    def report(self) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
        code = (
            "DEALT_WITH"
            if self.dealt_target_ids
            else "INTERRUPTED"
            if self.interrupted
            else "OBSERVED"
        )
        facts = list(self.observations)
        lines = list(self.observations.values())
        if self.dealt_target_ids:
            facts.append("anomaly_dealt_with")
            lines.append("現地で確認した異常個体には対処できました。")
        elif self.enemy_ids:
            facts.append("abnormal_urchin_present")
            lines.append("現地で異常個体を確認しました。")
        if self.interrupted and not self.dealt_target_ids:
            facts.append("visit_interrupted")
            lines.append("危険があり、確認を途中で切り上げました。")
        lines.append("異音の原因は、まだ確認できていません。")
        return code, tuple(facts), tuple(lines)


@dataclass
class FieldConversation:
    target_id: str
    lines: tuple[tuple[str, str], ...]
    index: int = 0


def observation_conversation(
    target_id: str, asked: set[str], repeated: bool, is_day: bool = True
) -> tuple[tuple[str, str], ...]:
    if repeated:
        return {
            "tap_stopped": (("ジャック", "水はまだ止まっているね。"),),
            "maintenance_unit": (("ヒューズ", "同じ区間で測定を続けているわ。"),),
            "observation_post": (("ジャック", "柱の様子は、さっき記録したとおりだね。"),),
        }.get(target_id, ())
    if target_id == "tap_stopped":
        lines = [
            ("ジャック", "蛇口を開けても、水が出ないね。"),
            ("ヒューズ", "供給が止まっているのね。この状態は記録しておきましょう。"),
        ]
        if "sound" in asked:
            lines += [
                ("ジャック", "ラメルさんの言ってた低い音は、今は聞こえないな。"),
                ("ヒューズ", "ええ。水が止まっていることと、音の原因は分けて考えたいわ。"),
            ]
        elif "damage" in asked:
            lines += [
                ("ジャック", "被害は分からないって言ってたね。奥の管までは見えないな。"),
                ("ヒューズ", "ここで確かめられたところだけ、残しておきましょう。"),
            ]
        return tuple(lines)
    if target_id == "maintenance_unit":
        lines = [
            ("ジャック", "小さな測定器だね。水の入った容器もある。"),
            ("ヒューズ", "水質を測るロボね。短い区間を往復しているわ。"),
        ]
        if "sound" in asked:
            lines += [
                ("ジャック", "この動きだけで、あの音の原因とは決められないね。"),
                ("ヒューズ", "そうね。動きと測定の様子を、まず記録しましょう。"),
            ]
        return tuple(lines)
    if target_id == "observation_post":
        lines = [
            ("ジャック", "柱はちゃんと立ってる。ここから周りを見ておこう。"),
            ("ヒューズ", "足元にも気をつけてね。近くの様子から確かめましょう。"),
        ]
        if "frequency" in asked and is_day:
            lines += [
                (
                    "ジャック",
                    "夜に聞こえるって言ってたね。昼間に静かでも、片づいたとは言えないか。",
                ),
                ("ヒューズ", "ええ。今見えたことと、夜の話は分けておきましょう。"),
            ]
        return tuple(lines)
    return ()


RETURN_TURNS = {
    "OBSERVED": (
        (
            ("ジャック", "見てきた範囲のことをお伝えしますね。"),
            ("ラメル", "はい。分かったところを聞かせてください。"),
        ),
        (
            ("ジャック", "今は浅瀬から離れていてください。何か変わったらお知らせください。"),
            ("ラメル", "分かりました。無理に見に行かず、連絡します。"),
        ),
    ),
    "DEALT_WITH": (
        (
            ("ジャック", "現地で分かったことをお伝えしますね。"),
            ("ラメル", "はい。あの辺り、大丈夫でしたか？"),
        ),
        (
            (
                "ジャック",
                "音については引き続き確認します。気づいたことがあればお知らせください。",
            ),
            ("ラメル", "分かりました。聞こえた時間を控えておきます。"),
        ),
    ),
    "INTERRUPTED": (
        (
            ("ジャック", "危険があったので、途中で戻りました。"),
            ("ラメル", "無事でよかったです。分かったところだけ教えてください。"),
        ),
        (
            ("ジャック", "まだ確認できていないところがあります。今は近寄らないでください。"),
            ("ラメル", "はい。私も近づかずに待ちます。"),
        ),
    ),
}
