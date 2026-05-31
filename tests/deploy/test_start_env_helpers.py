from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_save_env_value_creates_env_file_when_missing(tmp_path):
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    assert pwsh, "PowerShell is required to test deploy/start_env.ps1"

    env_file = tmp_path / ".env"
    script = f"""
. "$PWD/deploy/start_env.ps1"
Save-EnvValue -EnvFile "{env_file}" -Name "DEEPSEEK_API_KEY" -Value "sk-test"
if (-not (Test-Path "{env_file}")) {{ throw ".env was not created" }}
$content = Get-Content "{env_file}" -Raw
if ($content -notmatch 'DEEPSEEK_API_KEY="sk-test"') {{ throw "Key was not saved" }}
"""

    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_env_helpers_round_trip_quoted_special_characters(tmp_path):
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    assert pwsh, "PowerShell is required to test deploy/start_env.ps1"

    env_file = tmp_path / ".env"
    script = f"""
. "$PWD/deploy/start_env.ps1"
Save-EnvValue -EnvFile "{env_file}" -Name "DEEPSEEK_API_KEY" -Value 'sk-test"with\\slash'
Load-EnvFile -EnvFile "{env_file}"
if ($env:DEEPSEEK_API_KEY -ne 'sk-test"with\\slash') {{
  throw "Round-trip failed: $env:DEEPSEEK_API_KEY"
}}
"""

    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr or result.stdout
