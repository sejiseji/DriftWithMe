from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pyxel

APP_NAME = "drift-with-me-web"
FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
DEFAULT_OUTPUTS = ("index.html", "docs/index.html", "web/index.html")
DISABLED_GAMEPAD = 'gamepad: "disabled"'
WEB_HASH_LENGTH = 12


HOST_CSS = """:root {
  --drift-visible-width: 100vw;
  --drift-visible-height: 100svh;
  color-scheme: dark;
}

html,
body {
  margin: 0;
  width: var(--drift-visible-width);
  height: var(--drift-visible-height);
  overflow: hidden;
  background: #071016;
  overscroll-behavior: none;
}

body {
  position: fixed;
  inset: 0;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
}

#orientation-message {
  display: none;
  position: fixed;
  top: max(10px, env(safe-area-inset-top));
  left: max(12px, env(safe-area-inset-left));
  right: max(12px, env(safe-area-inset-right));
  z-index: 10;
  padding: 8px 10px;
  box-sizing: border-box;
  border: 1px solid rgba(243, 241, 223, 0.35);
  border-radius: 8px;
  background: rgba(7, 16, 22, 0.88);
  color: #f3f1df;
  font: 600 13px/1.35 system-ui, sans-serif;
  text-align: center;
  pointer-events: none;
}

body.drift-portrait #orientation-message {
  display: block;
}
"""


HOST_JS = """(() => {
  const root = document.documentElement;
  const body = document.body;

  const updateViewport = () => {
    const viewport = window.visualViewport;
    const width = viewport ? viewport.width : window.innerWidth;
    const height = viewport ? viewport.height : window.innerHeight;
    root.style.setProperty("--drift-visible-width", `${Math.floor(width)}px`);
    root.style.setProperty("--drift-visible-height", `${Math.floor(height)}px`);
    body.classList.toggle("drift-portrait", height > width);
  };

  updateViewport();
  window.addEventListener("resize", updateViewport, { passive: true });
  window.addEventListener("orientationchange", updateViewport, { passive: true });
  document.addEventListener("contextmenu", (event) => event.preventDefault());

  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", updateViewport, { passive: true });
    window.visualViewport.addEventListener("scroll", updateViewport, { passive: true });
  }
})();
"""


def copy_runtime_files(root: Path, app_dir: Path) -> None:
    if app_dir.exists():
        shutil.rmtree(app_dir)
    app_dir.mkdir(parents=True)
    shutil.copy2(root / "main.py", app_dir / "main.py")
    shutil.copytree(
        root / "src",
        app_dir / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
    )


def runtime_files(app_dir: Path) -> list[Path]:
    return sorted(path for path in app_dir.rglob("*") if path.is_file())


def write_zip_text(zf: zipfile.ZipFile, arcname: str, text: str) -> None:
    info = zipfile.ZipInfo(arcname, FIXED_ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, text.encode("utf-8"))


def write_zip_file(zf: zipfile.ZipFile, app_dir: Path, path: Path) -> None:
    arcname = str(Path(APP_NAME) / path.relative_to(app_dir))
    info = zipfile.ZipInfo(arcname, FIXED_ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, path.read_bytes())


def write_pyxapp(app_dir: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w") as zf:
        write_zip_text(zf, f"{APP_NAME}/{pyxel.APP_STARTUP_SCRIPT_FILE}", "main.py")
        for path in runtime_files(app_dir):
            write_zip_file(zf, app_dir, path)


def cache_busted_name(pyxapp: Path) -> str:
    digest = hashlib.sha256(pyxapp.read_bytes()).hexdigest()[:WEB_HASH_LENGTH]
    return f"{APP_NAME}-{digest}.pyxapp"


def write_host_assets(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "host.css").write_text(HOST_CSS, encoding="utf-8")
    (output_dir / "host.js").write_text(HOST_JS, encoding="utf-8")
    (output_dir / "manifest.webmanifest").write_text(
        json.dumps(
            {
                "name": "DriftWithMe E0",
                "short_name": "DriftWithMe",
                "description": "DriftWithMe Jack World P0 E0 Pyxel prototype.",
                "start_url": "./index.html",
                "scope": "./",
                "display": "fullscreen",
                "display_override": ["fullscreen", "standalone"],
                "orientation": "landscape",
                "background_color": "#071016",
                "theme_color": "#071016",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_html(root: Path, pyxapp: Path, output: Path) -> None:
    base64_string = base64.b64encode(pyxapp.read_bytes()).decode("ascii")
    pyxapp_name = json.dumps(cache_busted_name(pyxapp), ensure_ascii=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover, user-scalable=no">\n'
        '<meta name="apple-mobile-web-app-capable" content="yes">\n'
        '<meta name="apple-mobile-web-app-title" content="DriftWithMe">\n'
        '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n'
        '<meta name="mobile-web-app-capable" content="yes">\n'
        '<link rel="manifest" href="./manifest.webmanifest">\n'
        '<link rel="stylesheet" href="./host.css">\n'
        f'<script src="https://cdn.jsdelivr.net/gh/kitao/pyxel@{pyxel.VERSION}/wasm/pyxel.js"></script>\n'
        "</head>\n"
        "<body>\n"
        '<div id="orientation-message">'
        "横向き推奨です。画面ロックを解除して端末を横にしてください。"
        "</div>\n"
        '<script src="./host.js"></script>\n'
        "<script>\n"
        f'launchPyxel({{ command: "play", name: {pyxapp_name}, '
        f'{DISABLED_GAMEPAD}, base64: "{base64_string}" }});\n'
        "</script>\n"
        "</body>\n"
        "</html>\n",
        encoding="utf-8",
    )


def build_web(root: Path, outputs: list[Path]) -> tuple[Path, ...]:
    build_dir = root / "web" / "build"
    app_dir = build_dir / APP_NAME
    build_dir.mkdir(parents=True, exist_ok=True)
    copy_runtime_files(root, app_dir)

    pyxapp = build_dir / f"{APP_NAME}.pyxapp"
    pyxapp.unlink(missing_ok=True)
    write_pyxapp(app_dir, pyxapp)
    resolved_outputs = []
    for output in outputs:
        resolved = output if output.is_absolute() else root / output
        write_host_assets(resolved.parent)
        write_html(root, pyxapp, resolved)
        resolved_outputs.append(resolved)
    return tuple(resolved_outputs)


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build the DriftWithMe Pyxel web host.")
    parser.add_argument("--output", action="append", type=Path)
    args = parser.parse_args(argv)
    outputs = args.output or [Path(path) for path in DEFAULT_OUTPUTS]
    built = build_web(root, outputs)
    print("Built " + ", ".join(str(path.relative_to(root)) for path in built))
    print(f"Pyxel web runtime: {pyxel.VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
