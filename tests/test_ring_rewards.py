import pytest

from drift_with_me.ring_linkage import solution_counts
from drift_with_me.ring_puzzle import RingPuzzle
from drift_with_me.ring_rewards import RingRewardLedger


@pytest.mark.parametrize("help_used", [False, True])
def test_same_sunglasses_reward_both_routes_only_praise_differs_and_grant_is_idempotent(help_used):
    p = RingPuzzle.create()
    if help_used:
        p.assist()
    ledger = RingRewardLedger()
    assert not ledger.claim(p)
    for i, count in enumerate(solution_counts(p.angles, p.disabled_links)):
        for _ in range(min(count, 12 - count)):
            p.selected = i
            assert p.rotate(1 if count <= 6 else -1)
            p.tick(0.16)
    for seconds in (0.35, 1.4, 3.2):
        p.tick(seconds)
    assert p.clear_reward_available
    assert p.special_praise_earned is (not help_used)
    assert "サングラス" in p.completion_lines[0]
    assert ledger.claim(p)
    assert not ledger.claim(p)
    restored = RingRewardLedger.restore(ledger.snapshot())
    assert restored.sunglasses_received and not restored.claim(p)
    legacy = RingPuzzle.restore(p.snapshot())
    assert legacy.clear_reward_available and legacy.special_praise_earned is (not help_used)


def test_independent_preview_never_qualifies_and_invalid_ledger_is_rejected():
    p = RingPuzzle(angles=[0] * 5, phase="unlocked")
    assert not RingRewardLedger().claim(p)
    with pytest.raises(ValueError):
        RingRewardLedger.restore({"sunglasses_received": 1})
