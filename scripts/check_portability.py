"""Check current publishable text and prospective Git identities without mutations."""

from __future__ import annotations

import argparse
import base64
import io
import re
import subprocess
import zipfile
from pathlib import Path

APPROVED_NAME = "sejiseji"
APPROVED_EMAIL = "47272134+sejiseji@users.noreply.github.com"
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".js",
    ".css",
    ".html",
    ".sh",
    ".webmanifest",
}
HOME_PATH = re.compile(r"/(?:Users|home)/([^/\s`\"']+)|[A-Za-z]:[\\/]Users[\\/]([^\\/\s`\"']+)")
PLACEHOLDERS = {"user", "username", "example-user", "your-user", "USER", "USERNAME"}


def personal_path_lines(text: str) -> list[int]:
    result = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in HOME_PATH.finditer(line):
            user = next(value for value in match.groups() if value is not None)
            if user not in PLACEHOLDERS and not any(char in user for char in "<>${}"):
                result.append(number)
                break
    return result


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL
    )


def identity_allowed(identity: str) -> bool:
    match = re.fullmatch(r"(.*?) <([^<>]+)>(?: \d+ [+-]\d{4})?", identity.strip())
    return bool(match and match.groups() == (APPROVED_NAME, APPROVED_EMAIL))


def identity_issues(root: Path) -> list[str]:
    issues = []
    for kind in ("AUTHOR", "COMMITTER"):
        if not identity_allowed(git(root, "var", f"GIT_{kind}_IDENT")):
            issues.append(f"effective {kind.lower()} identity differs from the approved identity")
    try:
        upstream = git(root, "rev-parse", "--abbrev-ref", "@{upstream}").strip()
    except subprocess.CalledProcessError:
        issues.append("upstream unavailable: unpublished commit metadata was not checked")
        return issues
    records = git(
        root, "log", "--format=%h%x00%an <%ae>%x00%cn <%ce>%x00%B%x00%x1e", f"{upstream}..HEAD"
    )
    for record in records.split("\x1e"):
        fields = record.strip().split("\x00")
        if len(fields) < 4:
            continue
        commit, author, committer, message = fields[:4]
        if not identity_allowed(author) or not identity_allowed(committer):
            issues.append(f"commit {commit}: author or committer identity differs")
        for line in message.splitlines():
            if re.match(
                r"(?:Co-authored-by|Signed-off-by|Reviewed-by|Acked-by|Reported-by|Tested-by):",
                line,
                re.I,
            ) and not identity_allowed(line.split(":", 1)[1].strip()):
                issues.append(f"commit {commit}: unapproved identity trailer")
    return issues


def text_issues(label: str, data: bytes) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return []
    return [f"{label}:{line}: personal home path" for line in personal_path_lines(text)]


def archive_issues(label: str, data: bytes) -> list[str]:
    issues = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            name = member.filename
            if (
                name.startswith(("/", "\\"))
                or ".." in Path(name).parts
                or re.match(r"^[A-Za-z]:", name)
            ):
                issues.append(f"{label}: non-relative archive entry")
            if Path(name).suffix.lower() in TEXT_SUFFIXES:
                if member.file_size > 20_000_000:
                    issues.append(f"{label}: text entry exceeds inspection limit")
                else:
                    issues.extend(text_issues(f"{label}!{name}", archive.read(member)))
    return issues


def source_issues(root: Path) -> list[str]:
    issues = []
    names = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\x00")
    for name in sorted(set(names)):
        path = root / name
        if not name or not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        data = path.read_bytes()
        issues.extend(text_issues(name, data))
        if path.suffix == ".html":
            text = data.decode("utf-8")
            for payload in re.findall(r"[A-Za-z0-9+/]{100,}={0,2}", text):
                try:
                    decoded = base64.b64decode(payload, validate=True)
                    if decoded.startswith(b"PK\x03\x04"):
                        issues.extend(archive_issues(name, decoded))
                except (ValueError, zipfile.BadZipFile):
                    issues.append(f"{name}: embedded archive could not be inspected")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        issues = source_issues(args.root) + identity_issues(args.root)
    except (OSError, subprocess.CalledProcessError, zipfile.BadZipFile):
        print("portability: FAIL (inspection could not complete; details withheld)")
        return 1
    for issue in issues:
        print(issue)
    print(f"portability: {'FAIL' if issues else 'PASS'}")
    return bool(issues)


if __name__ == "__main__":
    raise SystemExit(main())
