"""Story reward contract; debug previews never apply this ledger to game inventory."""

from dataclasses import dataclass


@dataclass
class RingRewardLedger:
    sunglasses_received: bool = False

    def claim(self, puzzle) -> bool:
        """Return true only for the first completed linked puzzle, regardless of help."""
        if not puzzle.clear_reward_available or self.sunglasses_received:
            return False
        self.sunglasses_received = True
        return True

    def snapshot(self):
        return {"sunglasses_received": self.sunglasses_received}

    @classmethod
    def restore(cls, raw=None):
        if raw is None:
            return cls()
        if (
            not isinstance(raw, dict)
            or set(raw) != {"sunglasses_received"}
            or type(raw["sunglasses_received"]) is not bool
        ):
            raise ValueError("invalid ring reward ledger")
        return cls(raw["sunglasses_received"])
