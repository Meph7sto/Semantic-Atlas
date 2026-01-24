#requires -Version 5.1
$ErrorActionPreference = "Stop"

# 项目根目录（脚本位于 deploy/ 下）
$BASE_DIR = Split-Path -Parent $PSScriptRoot
$DeployDir = Join-Path $BASE_DIR "deploy"
$NginxPidPath = Join-Path $DeployDir "logs/nginx.pid"
$NginxConf = Join-Path $DeployDir "nginx.generated.conf"

function Stop-ProcessTree {
  param(
    [int]$ProcessId,
    [string]$Label
  )
  if (-not $ProcessId -or $ProcessId -le 0) { return }
  try {
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
      Stop-ProcessTree -ProcessId $child.ProcessId -Label $Label
    }
  }
  catch {
  }
  try {
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
  }
  catch {
  }
}

Write-Host "[stop] 尝试停止 Nginx..."
$NginxExe = $null
$LocalNginxPath = Join-Path $DeployDir "nginx-1.26.1/nginx.exe"
if (Test-Path $LocalNginxPath) {
  $NginxExe = $LocalNginxPath
}
else {
  $NginxCmd = Get-Command nginx -ErrorAction SilentlyContinue
  if ($NginxCmd) {
    $NginxExe = $NginxCmd.Source
  }
}
if ($NginxExe) {
  try {
    & $NginxExe -c $NginxConf -p $DeployDir -g "pid logs/nginx.pid;" -s stop
  } catch {
    Write-Warning "停止 Nginx 时出错: $_"
  }
}
if (Test-Path $NginxPidPath) {
  try {
    $nginxProcIdText = (Get-Content $NginxPidPath -Raw).Trim()
    if ($nginxProcIdText) {
      $nginxProcId = [int]$nginxProcIdText
      Stop-ProcessTree -ProcessId $nginxProcId -Label "nginx"
    }
  } catch {
    Write-Warning "根据 pid 文件停止 Nginx 失败: $_"
  }
  Remove-Item $NginxPidPath -Force -ErrorAction SilentlyContinue
}
try {
  $nginxMatches = Get-CimInstance Win32_Process -Filter "Name='nginx.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($NginxConf) }
  foreach ($proc in $nginxMatches) {
    Stop-ProcessTree -ProcessId $proc.ProcessId -Label "nginx"
  }
}
catch {
}

Write-Host "[stop] 结束占用端口的进程: 8000 (FastAPI), 5001 (Flask), 8008 (Nginx)"
$ports = @(8000, 5001, 8008)
foreach ($port in $ports) {
  $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
  if ($conns) {
    $pids = $conns | Where-Object { $_.OwningProcess -gt 0 } | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
      Write-Host (" - port {0}: PID {1} -> stopping" -f $port, $procId)
      Stop-ProcessTree -ProcessId $procId -Label "port $port"
    }
  }
}

try {
  $pythonMatches = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and (
        $_.CommandLine -match "backend_inference" -or
        $_.CommandLine -match "backend_business[/\\]app.py"
      )
    }
  foreach ($proc in $pythonMatches) {
    Write-Host (" - python PID {0} -> stopping" -f $proc.ProcessId)
    Stop-ProcessTree -ProcessId $proc.ProcessId -Label "python"
  }
}
catch {
}

Write-Host "[stop] 完成。"
