"""Five direct links over Z/12; remove the back-link first for safe assistance."""

STEPS = 12
# Stable identities: the four former outward links, then the new 4 -> 3 back-link.
LINKS = ((0, 1, 1), (1, 2, -1), (2, 3, 1), (3, 4, 1), (3, 2, -1))
LINK_SIGNS = (1, -1, 1, 1)
ASSIST_ORDER = (4, 0, 1, 2, 3)
RULESET = "adjacent_five_v2"
SCRAMBLE = ((0, 1), (1, -1), (2, 1), (2, 1), (3, -1), (3, -1), (4, 1))


def move_deltas(selected: int, direction: int, disabled=(), *, linked=True) -> list[int]:
    delta = [0] * 5
    delta[selected] = direction
    if linked:
        for index, (source, target, sign) in enumerate(LINKS):
            if source == selected and index not in disabled:
                delta[target] += direction * sign
    return delta


def apply_move(angles, selected, direction, disabled=()):
    return tuple(
        (a + d) % STEPS
        for a, d in zip(angles, move_deltas(selected, direction, disabled), strict=True)
    )


def scramble():
    angles = (0,) * 5
    for selected, direction in SCRAMBLE:
        angles = apply_move(angles, selected, direction)
    return angles


LINKED_INITIAL = scramble()


def all_solution_counts(angles, disabled=()) -> tuple[tuple[int, ...], ...]:
    """Solve the 3/4 block without dividing by a non-unit modulo12."""
    c0 = -angles[0] % STEPS
    c1 = (-angles[1] - (c0 if 0 not in disabled else 0)) % STEPS
    forward, back = 2 not in disabled, 4 not in disabled
    rhs = (-angles[3] + (angles[2] - (c1 if 1 not in disabled else 0) if forward else 0)) % STEPS
    if forward and back:
        if rhs % 2:
            return ()
        c3_options = (rhs // 2, rhs // 2 + 6)
    else:
        c3_options = (rhs,)
    result = []
    for c3 in c3_options:
        c2 = (-angles[2] + (c1 if 1 not in disabled else 0) + (c3 if back else 0)) % STEPS
        c4 = (-angles[4] - (c3 if 3 not in disabled else 0)) % STEPS
        result.append((c0, c1, c2, c3, c4))
    return tuple(result)


def solution_counts(angles, disabled=()) -> tuple[int, ...]:
    options = all_solution_counts(angles, disabled)
    if not options:
        raise ValueError("state is not reachable under these links")
    return min(options, key=lambda counts: sum(min(c, STEPS - c) for c in counts))
