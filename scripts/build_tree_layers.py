from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

COLKEY = "8"
WOOD_CORE = frozenset("49A")
WOOD_DETAIL = frozenset("01249AEF")
LEAF_HIGHLIGHTS = frozenset("BCEF")
FOLIAGE_SOURCE_SHIFT_PX = 2
FOLIAGE_SWAY_STAGES = 3


@dataclass(frozen=True)
class TreeLayerSpec:
    source_name: str
    centerline: tuple[tuple[int, int], ...]
    static_base_y: int


TREE_LAYER_SPECS = (
    TreeLayerSpec(
        source_name="tree_leafy_a",
        centerline=((51, 42), (49, 65), (48, 95), (48, 112)),
        static_base_y=111,
    ),
    TreeLayerSpec(
        source_name="tree_thin_b",
        centerline=((49, 28), (49, 40), (48, 70), (48, 105), (48, 113)),
        static_base_y=112,
    ),
)


def neighboring_points(x: int, y: int, width: int, height: int):
    for offset_y in (-1, 0, 1):
        for offset_x in (-1, 0, 1):
            if offset_x == 0 and offset_y == 0:
                continue
            neighbor_x = x + offset_x
            neighbor_y = y + offset_y
            if 0 <= neighbor_x < width and 0 <= neighbor_y < height:
                yield neighbor_x, neighbor_y


def interpolated_center_x(points: tuple[tuple[int, int], ...], y: int) -> float:
    before = max((point for point in points if point[1] <= y), key=lambda point: point[1])
    after = min((point for point in points if point[1] >= y), key=lambda point: point[1])
    if before[1] == after[1]:
        return float(before[0])
    progress = (y - before[1]) / (after[1] - before[1])
    return before[0] + (after[0] - before[0]) * progress


def split_tree_layers(
    rows: tuple[str, ...],
    spec: TreeLayerSpec,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    height = len(rows)
    width = len(rows[0])
    wood = {
        (x, y) for y, row in enumerate(rows) for x, color in enumerate(row) if color in WOOD_CORE
    }
    wood.update(
        (x, y)
        for y, row in enumerate(rows)
        for x, color in enumerate(row)
        if color in WOOD_DETAIL
        and any(point in wood for point in neighboring_points(x, y, width, height))
    )
    wood.update(
        (x, y)
        for y, row in enumerate(rows)
        for x, color in enumerate(row)
        if y >= spec.static_base_y and color != COLKEY
    )

    trunk = [[COLKEY] * width for _ in range(height)]
    leaves = [[COLKEY] * width for _ in range(height)]
    for y, row in enumerate(rows):
        for x, color in enumerate(row):
            target = trunk if (x, y) in wood else leaves
            target[y][x] = color

    first_y = spec.centerline[0][1]
    last_y = min(spec.static_base_y, spec.centerline[-1][1] + 1)
    for y in range(first_y, last_y):
        center = round(interpolated_center_x(spec.centerline, y))
        half_width = 1 if y < 72 else 2
        for x in range(center - half_width, center + half_width + 1):
            if rows[y][x] == COLKEY or trunk[y][x] != COLKEY:
                continue
            delta = x - center
            if delta == -half_width:
                color = "2"
            elif delta == half_width:
                color = "4"
            elif delta <= 0:
                color = "9"
            else:
                color = "A"
            trunk[y][x] = color

    trunk_rows = tuple("".join(row) for row in trunk)
    leaf_rows = tuple("".join(row) for row in leaves)
    recomposed = tuple(
        "".join(
            leaf_color if leaf_color != COLKEY else trunk_color
            for trunk_color, leaf_color in zip(trunk_row, leaf_row, strict=True)
        )
        for trunk_row, leaf_row in zip(trunk_rows, leaf_rows, strict=True)
    )
    if recomposed != rows:
        raise ValueError(f"{spec.source_name}: layer recomposition changed source pixels")
    return trunk_rows, leaf_rows


def matching_runs(row: str, colors: frozenset[str]) -> tuple[tuple[int, int], ...]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for x, color in enumerate(row + COLKEY):
        matches = color in colors
        if matches and start is None:
            start = x
        elif not matches and start is not None:
            runs.append((start, x - 1))
            start = None
    return tuple(runs)


def foliage_candidate_score(
    source_name: str,
    kind: str,
    y: int,
    start: int,
    end: int,
) -> int:
    seed = sum((index + 1) * ord(char) for index, char in enumerate(source_name + kind))
    value = seed ^ (y * 73856093) ^ (start * 19349663) ^ (end * 83492791)
    value ^= value >> 13
    value *= 1274126177
    return value ^ (value >> 16)


def build_foliage_right_sway(
    rows: tuple[str, ...],
    source_name: str,
) -> tuple[tuple[str, ...], ...]:
    """Build cumulative local changes for one coherent rightward sway and return."""
    height = len(rows)
    width = len(rows[0])
    leaf_colors = frozenset(char for row in rows for char in row if char != COLKEY)
    leaf_pixel_count = sum(char != COLKEY for row in rows for char in row)
    changed: set[tuple[int, int]] = set()
    operations: list[tuple[int, int, tuple[tuple[int, str], ...]]] = []

    edge_candidates: list[tuple[int, int, int, int]] = []
    for y, row in enumerate(rows):
        for start, end in matching_runs(row, leaf_colors):
            if end - start + 1 < FOLIAGE_SOURCE_SHIFT_PX * 2:
                continue
            destinations = range(end + 1, end + FOLIAGE_SOURCE_SHIFT_PX + 1)
            if end + FOLIAGE_SOURCE_SHIFT_PX >= width:
                continue
            if any(row[x] != COLKEY for x in destinations):
                continue
            score = foliage_candidate_score(source_name, "contour", y, start, end)
            edge_candidates.append((score, y, start, end))

    edge_target = max(8, round(leaf_pixel_count / 300))
    for score, y, start, end in sorted(edge_candidates)[:edge_target]:
        source_xs = range(start, start + FOLIAGE_SOURCE_SHIFT_PX)
        destination_xs = range(end + 1, end + FOLIAGE_SOURCE_SHIFT_PX + 1)
        edge_colors = rows[y][end - FOLIAGE_SOURCE_SHIFT_PX + 1 : end + 1]
        updates = tuple((x, COLKEY) for x in source_xs) + tuple(
            zip(destination_xs, edge_colors, strict=True)
        )
        operations.append((score, y, updates))
        changed.update((x, y) for x, _color in updates)

    highlight_candidates: list[tuple[int, int, int, int]] = []
    for y, row in enumerate(rows):
        for start, end in matching_runs(row, LEAF_HIGHLIGHTS):
            previous_x = start - 1
            next_x = end + 1
            if previous_x < 0 or next_x >= width:
                continue
            if row[previous_x] == COLKEY or row[next_x] == COLKEY:
                continue
            if row[next_x] in LEAF_HIGHLIGHTS:
                continue
            if (start, y) in changed or (next_x, y) in changed:
                continue
            score = foliage_candidate_score(source_name, "highlight", y, start, end)
            highlight_candidates.append((score, y, start, end))

    highlight_target = max(4, round(leaf_pixel_count / 650))
    applied_highlights = 0
    for _score, y, start, end in sorted(highlight_candidates):
        next_x = end + 1
        if (start, y) in changed or (next_x, y) in changed:
            continue
        updates = ((start, rows[y][start - 1]), (next_x, rows[y][end]))
        operations.append((_score, y, updates))
        changed.update((x, y) for x, _color in updates)
        applied_highlights += 1
        if applied_highlights >= highlight_target:
            break

    groups: list[list[tuple[int, tuple[tuple[int, str], ...]]]] = [
        [] for _ in range(FOLIAGE_SWAY_STAGES)
    ]
    for index, (_score, y, updates) in enumerate(sorted(operations)):
        groups[index % FOLIAGE_SWAY_STAGES].append((y, updates))

    variants: list[tuple[str, ...]] = []
    active_operations: list[tuple[int, tuple[tuple[int, str], ...]]] = []
    for group in groups:
        active_operations.extend(group)
        output = [list(row) for row in rows]
        for y, updates in active_operations:
            for x, color in updates:
                output[y][x] = color
        result = tuple("".join(row) for row in output)
        if len(result) != height or {len(row) for row in result} != {width}:
            raise ValueError(f"{source_name}: invalid foliage sway dimensions")
        variants.append(result)
    return tuple(variants)


def write_or_check(path: Path, rows: tuple[str, ...], check: bool) -> bool:
    content = "\n".join(rows) + "\n"
    if check:
        return path.exists() and path.read_text(encoding="utf-8") == content
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    asset_dir = root / "src/drift_with_me/assets"
    stale: list[str] = []
    for spec in TREE_LAYER_SPECS:
        source_path = asset_dir / f"{spec.source_name}.hex"
        rows = tuple(source_path.read_text(encoding="utf-8").strip().splitlines())
        if len(rows) != 128 or {len(row) for row in rows} != {96}:
            raise ValueError(f"{source_path}: expected 96x128 source")
        trunk_rows, leaf_rows = split_tree_layers(rows, spec)
        sway_stages = build_foliage_right_sway(leaf_rows, spec.source_name)
        outputs = [("trunk", trunk_rows), ("leaves", leaf_rows)]
        outputs.extend(
            (f"leaves_sway_right_{index:02d}", stage_rows)
            for index, stage_rows in enumerate(sway_stages, start=1)
        )
        for suffix, layer_rows in outputs:
            output = asset_dir / f"{spec.source_name}_{suffix}.hex"
            if not write_or_check(output, layer_rows, args.check):
                stale.append(str(output.relative_to(root)))
    if stale:
        print("stale tree layers: " + ", ".join(stale))
        return 1
    print("PASS: tree foliage/trunk layers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
