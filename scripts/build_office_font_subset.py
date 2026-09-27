from __future__ import annotations

import argparse
import string
from pathlib import Path

import pyxel

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BDF = Path(pyxel.__file__).resolve().parent / "examples/assets/umplus_j12r.bdf"
TARGET_BDF = ROOT / "src/drift_with_me/assets/fonts/umplus_j12r_office.bdf"
SOURCE_SUFFIXES = {".json", ".py"}
ASCII_PRINTABLE = "".join(
    char for char in string.printable if char not in {"\t", "\n", "\r", "\x0b", "\x0c"}
)


def required_codepoints() -> set[int]:
    text = ASCII_PRINTABLE
    source_root = ROOT / "src/drift_with_me"
    for path in sorted(source_root.rglob("*")):
        if path.is_file() and path.suffix in SOURCE_SUFFIXES:
            text += path.read_text(encoding="utf-8")
    return {ord(char) for char in text if ord(char) >= 32} | {ord("?"), 0x3000}


def read_bdf(path: Path) -> tuple[list[str], dict[int, list[str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    chars_index = next(index for index, line in enumerate(lines) if line.startswith("CHARS "))
    glyphs: dict[int, list[str]] = {}
    index = chars_index + 1
    # umplus_j12r concatenates the Japanese and half-width Latin BDF sections.
    # Keep scanning after the first ENDFONT so mixed Japanese/ASCII strings use
    # the same runtime font.
    while index < len(lines):
        if not lines[index].startswith("STARTCHAR "):
            index += 1
            continue
        start = index
        encoding: int | None = None
        while index < len(lines) and lines[index] != "ENDCHAR":
            if lines[index].startswith("ENCODING "):
                encoding = int(lines[index].split()[1])
            index += 1
        if encoding is not None:
            glyphs[encoding] = lines[start : index + 1]
        index += 1
    return lines[:chars_index], glyphs


def generated_subset() -> str:
    header, source_glyphs = read_bdf(SOURCE_BDF)
    required = required_codepoints()
    missing = sorted(required - set(source_glyphs))
    if missing:
        shown = ", ".join(f"U+{codepoint:04X}" for codepoint in missing[:24])
        suffix = " ..." if len(missing) > 24 else ""
        raise SystemExit(f"missing glyphs in {SOURCE_BDF}: {shown}{suffix}")

    ordered = sorted(required)
    lines = [*header, f"CHARS {len(ordered)}"]
    for codepoint in ordered:
        lines.extend(source_glyphs[codepoint])
    lines.append("ENDFONT")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = generated_subset()
    if args.check:
        current = TARGET_BDF.read_text(encoding="utf-8") if TARGET_BDF.exists() else ""
        if current != generated:
            raise SystemExit(f"stale office font subset: {TARGET_BDF.relative_to(ROOT)}")
        print(f"PASS: {TARGET_BDF.relative_to(ROOT)}")
        return
    TARGET_BDF.parent.mkdir(parents=True, exist_ok=True)
    TARGET_BDF.write_text(generated, encoding="utf-8")
    print(f"wrote {TARGET_BDF.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
