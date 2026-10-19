from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("exit_code", [0, 23])
def test_launcher_preserves_exit_code_and_keeps_failure_visible(tmp_path, exit_code):
    shutil.copy2(REPO_ROOT / "start.bat", tmp_path / "start.bat")
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / "start.ps1").write_text(
        f"param([string]$Mode)\nWrite-Host \"TEST_MODE=$Mode\"\nexit {exit_code}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "start.bat", "-Mode", "backend"],
        cwd=tmp_path,
        input="\n",
        capture_output=True,
        text=True,
        errors="replace",
        timeout=20,
    )
    assert result.returncode == exit_code, result.stdout + result.stderr
    assert "TEST_MODE=backend" in result.stdout
    assert ("Startup failed with exit code 23" in result.stdout) == (exit_code != 0)
