from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_powershell(body):
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    assert pwsh, "PowerShell is required"
    script = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
  "$PWD/deploy/start.ps1", [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw ($parseErrors | Out-String) }
$ast.FindAll({param($node)
  $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
}, $false) | ForEach-Object { Invoke-Expression $_.Extent.Text }
$env:DOCKER_HOST = $null
""" + body + "\nexit 0\n"
    result = subprocess.run(
        [pwsh, "-NoProfile", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_running_engine_does_not_start_desktop():
    run_powershell("""
function FakeDocker { $global:LASTEXITCODE = 0 }
function Start-Process { throw 'Unexpected launch' }
Wait-DockerEngine -DockerExe FakeDocker
""")


def test_unavailable_remote_engine_fails_without_starting_desktop():
    run_powershell("""
function FakeDocker {
  $global:LASTEXITCODE = 1
  if ($args[0] -eq 'context') { 'remote' }
}
function Start-Process { throw 'Unexpected launch' }
try { Wait-DockerEngine -DockerExe FakeDocker; throw 'Expected failure' }
catch { if ($_ -notmatch 'Docker engine is unavailable') { throw } }
""")


@pytest.mark.parametrize("ready", [True, False])
def test_desktop_start_and_readiness_timeout(ready):
    run_powershell("""
$script:checks = 0
$script:launched = $false
$script:clock = [datetime]'2026-01-01'
function FakeDocker {
  if ($args[0] -eq 'context') { 'desktop-linux'; return }
  $script:checks++
  $global:LASTEXITCODE = 1
  if (READY -and $script:checks -gt 1) { $global:LASTEXITCODE = 0 }
}
function Test-Path { return $true }
function Get-Process { return $null }
function Start-Process {
  param($FilePath, $WindowStyle)
  if ($WindowStyle -ne 'Hidden') { throw 'Expected hidden launch' }
  $script:launched = $true
}
function Start-Sleep { }
function Get-Date {
  $script:clock = $script:clock.AddSeconds(121)
  return $script:clock
}
try {
  Wait-DockerEngine -DockerExe FakeDocker
  if (-not READY) { throw 'Expected timeout' }
} catch {
  if (READY -or $_ -notmatch 'did not become ready') { throw }
}
if (-not $script:launched) { throw 'Desktop was not launched' }
""".replace("READY", "$true" if ready else "$false"))


def test_required_command_propagates_failure():
    run_powershell("""
function Resolve-NativeCommandPath { return 'FakeCompose' }
function FakeCompose { $global:LASTEXITCODE = 17 }
try {
  Invoke-RequiredNativeCommand -FilePath docker -ArgumentList @('compose', 'up') -WorkingDirectory $PWD -StepName 'PostgreSQL docker compose'
  throw 'Expected failure'
} catch { if ($_ -notmatch 'failed with exit code 17') { throw } }
""")
