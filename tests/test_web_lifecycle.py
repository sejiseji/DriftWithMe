import shutil
import subprocess
from pathlib import Path

import pytest
from scripts.build_web import HOST_JS


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required for actual host execution")
def test_actual_host_lifecycle_gates_frames_audio_and_input_without_duplicate_loops():
    harness = Path(__file__).parent / "fixtures/web_lifecycle_harness.cjs"
    result = subprocess.run(
        ["node", str(harness)], input=HOST_JS, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "zerohiddenframes" in result.stdout
