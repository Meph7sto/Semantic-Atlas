#requires -Version 5.1
$ErrorActionPreference = "Stop"

# 项目根目录（脚本位于 deploy/ 下）
$BASE_DIR = Split-Path -Parent $PSScriptRoot
$DeployDir = Join-Path $BASE_DIR "deploy"
$NginxPidPath = Join-Path $DeployDir "logs/nginx.pid"
$NginxConf = Join-Path $DeployDir "nginx.generated.conf"
$Script:StoppedPids = [System.Collections.Generic.HashSet[int]]::new()
$TaskKillExe = Get-Command taskkill.exe -ErrorAction SilentlyContinue

function Stop-ProcessTree {
  param(
    [int]$ProcessId,
    [string]$Label = "process"
  )

  if (-not $ProcessId -or $ProcessId -le 0) { return }
  if (-not $Script:StoppedPids.Add($ProcessId)) { return }

  try {
    if ($TaskKillExe) {
      # taskkill /T 一次性结束进程树，避免反复 WMI 递归查询带来的性能开销
      & $TaskKillExe.Source /PID $ProcessId /T /F *> $null
      return
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

function Get-ProcessMatches {
  param(
    [string]$Name,
    [scriptblock]$Predicate
  )

  try {
    $matches = Get-CimInstance Win32_Process -Filter "Name='$Name'" -ErrorAction SilentlyContinue
    if (-not $matches) { return @() }
    return @($matches | Where-Object $Predicate)
  }
  catch {
    return @()
  }
}

function Stop-PidList {
  param(
    [int[]]$ProcessIds,
    [string]$Label
  )

  if (-not $ProcessIds) { return }

  foreach ($targetPid in ($ProcessIds | Where-Object { $_ -gt 0 } | Select-Object -Unique)) {
    Write-Host (" - {0}: PID {1} -> stopping" -f $Label, $targetPid)
    Stop-ProcessTree -ProcessId $targetPid -Label $Label
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

if ($NginxExe -and (Test-Path $NginxPidPath)) {
  try {
    & $NginxExe -c $NginxConf -p $DeployDir -g "pid logs/nginx.pid;" -s stop
  }
  catch {
    Write-Warning "停止 Nginx 时出错: $_"
  }
}

$nginxPidFromFile = $null
if (Test-Path $NginxPidPath) {
  try {
    $nginxProcIdText = (Get-Content $NginxPidPath -Raw).Trim()
    if ($nginxProcIdText) {
      $nginxPidFromFile = [int]$nginxProcIdText
      Stop-PidList -ProcessIds @($nginxPidFromFile) -Label "nginx"
    }
  }
  catch {
    Write-Warning "根据 pid 文件停止 Nginx 失败: $_"
  }
  Remove-Item $NginxPidPath -Force -ErrorAction SilentlyContinue
}

$nginxMatches = Get-ProcessMatches -Name "nginx.exe" -Predicate {
  $_.CommandLine -and $_.CommandLine -match [regex]::Escape($NginxConf)
}

if ($nginxMatches.Count -gt 0) {
  $allPids = @($nginxMatches | Select-Object -ExpandProperty ProcessId)
  $masterPids = @($nginxMatches | Where-Object { $_.ParentProcessId -notin $allPids } | Select-Object -ExpandProperty ProcessId)
  $workerPids = @($nginxMatches | Where-Object { $_.ParentProcessId -in $allPids } | Select-Object -ExpandProperty ProcessId)
  Stop-PidList -ProcessIds $masterPids -Label "nginx master"
  Stop-PidList -ProcessIds $workerPids -Label "nginx worker"
}

Start-Sleep -Milliseconds 200
$nginxLeft = Get-ProcessMatches -Name "nginx.exe" -Predicate {
  $_.CommandLine -and $_.CommandLine -match [regex]::Escape($NginxConf)
}
if ($nginxLeft.Count -gt 0) {
  Write-Warning "Nginx 停止失败，可能有残留进程。"
}
else {
  Write-Host "Nginx 已停止或未运行。"
}

Write-Host "[stop] 结束占用端口的进程: 8000 (FastAPI Inference), 5002 (FastAPI Business), 8008 (Nginx), 5173 (Vite Dev)"
$ports = @(8000, 5002, 8008, 5173)

try {
  $listenConns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in $ports -and $_.OwningProcess -gt 0 }

  foreach ($port in $ports) {
    $portPids = @($listenConns | Where-Object { $_.LocalPort -eq $port } | Select-Object -ExpandProperty OwningProcess -Unique)
    Stop-PidList -ProcessIds $portPids -Label ("port {0}" -f $port)
  }
}
catch {
}

$pythonMatches = Get-ProcessMatches -Name "python.exe" -Predicate {
  $_.CommandLine -and (
    $_.CommandLine -match "backend_inference" -or
    $_.CommandLine -match "backend_business[/\\]main.py" -or
    $_.CommandLine -match "uvicorn.*backend_business.main"
  )
}
Stop-PidList -ProcessIds @($pythonMatches | Select-Object -ExpandProperty ProcessId) -Label "python"

$nodeMatches = Get-ProcessMatches -Name "node.exe" -Predicate {
  $_.CommandLine -and $_.CommandLine -match "vite"
}
Stop-PidList -ProcessIds @($nodeMatches | Select-Object -ExpandProperty ProcessId) -Label "node"

Write-Host "[stop] 检查 FRP 客户端..."
$FrpPidPath = Join-Path $DeployDir "logs/frpc.pid"
if (Test-Path $FrpPidPath) {
  try {
    $frpPidText = (Get-Content $FrpPidPath -Raw).Trim()
    if ($frpPidText) {
      $frpPid = [int]$frpPidText
      Stop-PidList -ProcessIds @($frpPid) -Label "frpc"
    }
  }
  catch {
    Write-Warning "根据 pid 文件停止 frpc 失败: $_"
  }
  Remove-Item $FrpPidPath -Force -ErrorAction SilentlyContinue
}

$frpMatches = Get-ProcessMatches -Name "frpc.exe" -Predicate { $true }
Stop-PidList -ProcessIds @($frpMatches | Select-Object -ExpandProperty ProcessId) -Label "frpc"

Write-Host "[stop] 完成。"
