from __future__ import annotations

import json
import re
from pathlib import Path

from scripts import build_web

ROOT = Path(__file__).resolve().parents[1]


def test_web_host_references_cache_busted_host_assets(tmp_path: Path) -> None:
    pyxapp = tmp_path / "test.pyxapp"
    pyxapp.write_bytes(b"test-pyxapp")
    web_manifest = build_web.manifest_text("./index.html?v=test-build")

    output = tmp_path / "index.html"
    build_web.write_html(ROOT, pyxapp, output, web_manifest)

    html = output.read_text(encoding="utf-8")
    assert re.search(r'href="./manifest\.webmanifest\?v=[0-9a-f]{12}"', html)
    assert re.search(r'href="./host\.css\?v=[0-9a-f]{12}"', html)
    assert re.search(r'src="./host\.js\?v=[0-9a-f]{12}"', html)
    assert 'href="./manifest.webmanifest">' not in html
    assert '<script src="./host.js"></script>' not in html


def test_web_manifest_start_url_uses_pyxapp_build_version(tmp_path: Path) -> None:
    pyxapp = tmp_path / "test.pyxapp"
    pyxapp.write_bytes(b"test-pyxapp")

    version = build_web.cache_busted_version(pyxapp)
    data = json.loads(build_web.manifest_text(f"./index.html?v={version}"))

    assert data["start_url"] == f"./index.html?v={version}"
    assert version.startswith("drift-with-me-web-")
    assert data["scope"] == "./"
