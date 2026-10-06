from __future__ import annotations

import io
import zipfile
from pathlib import Path

from scripts import check_portability as checker


def home_path(user: str) -> str:
    return "/" + "Users/" + user + "/project"


def test_home_paths_and_legitimate_examples() -> None:
    text = "\n".join(
        [
            home_path("private-person"),
            home_path("<username>"),
            home_path("example-user"),
            "https://example.org/project",
            "file://" + home_path("private-person"),
        ]
    )
    assert checker.personal_path_lines(text) == [1, 5]
    assert checker.personal_path_lines("C:" + "\\Users\\private-person\\project") == [1]


def test_archive_checks_text_without_binary_false_positives() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("image.png", home_path("private-person").encode())
        archive.writestr("app.py", "ROOT=" + repr(home_path("private-person")))
        archive.writestr("../escape.txt", "safe")
    issues = checker.archive_issues("package", stream.getvalue())
    assert len(issues) == 2
    assert "app.py:1" in issues[0]
    assert "non-relative" in issues[1]
    assert "private-person" not in "\n".join(issues)


def test_effective_overrides_and_only_unpublished_commits(monkeypatch) -> None:
    approved = f"{checker.APPROVED_NAME} <{checker.APPROVED_EMAIL}>"
    calls = []

    def fake_git(root, *args):
        calls.append(args)
        if args[0] == "var":
            return (
                approved + " 123 +0000"
                if "AUTHOR" in args[1]
                else "Other <other@example.org> 123 +0000"
            )
        if args[0] == "rev-parse":
            return "origin/main\n"
        return (
            "abc123\x00"
            + approved
            + "\x00"
            + approved
            + "\x00Co-authored-by: Other <other@example.org>\x00\x1e"
        )

    monkeypatch.setattr(checker, "git", fake_git)
    issues = checker.identity_issues(Path("."))
    assert len(issues) == 2
    assert calls[-1][-1] == "origin/main..HEAD"
    assert "other@example.org" not in "\n".join(issues)


def test_unavailable_upstream_is_reported(monkeypatch) -> None:
    import subprocess

    def fake_git(root, *args):
        if args[0] == "var":
            return f"{checker.APPROVED_NAME} <{checker.APPROVED_EMAIL}> 123 +0000"
        raise subprocess.CalledProcessError(1, ["git"])

    monkeypatch.setattr(checker, "git", fake_git)
    assert "upstream unavailable" in checker.identity_issues(Path("."))[0]
