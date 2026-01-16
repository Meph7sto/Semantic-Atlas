#requires -Version 5.1
$ErrorActionPreference = "Stop"

# 项目根目录（脚本位于 deploy/ 下）
$BASE_DIR = Split-Path -Parent $PSScriptRoot
$DeployDir = Join-Path $BASE_DIR "deploy"
$NginxPidPath = Join-Path $DeployDir "logs/nginx.pid"
$NginxConf = Join-Path $DeployDir "nginx.generated.conf"

Write-Host "[stop] 尝试停止 Nginx..."
$NginxCmd = Get-Command nginx -ErrorAction SilentlyContinue
if ($NginxCmd) {
  try {
    & $NginxCmd.Source -c $NginxConf -p $DeployDir -g "pid logs/nginx.pid;" -s stop
  } catch {
    Write-Warning "停止 Nginx 时出错: $_"
  }
}
if (Test-Path $NginxPidPath) {
  try {
    $nginxProcId = Get-Content $NginxPidPath
    Stop-Process -Id $nginxProcId -Force -ErrorAction SilentlyContinue
  } catch {
    Write-Warning "根据 pid 文件停止 Nginx 失败: $_"
  }
  Remove-Item $NginxPidPath -Force -ErrorAction SilentlyContinue
}

Write-Host "[stop] 结束占用端口的进程: 8000 (FastAPI), 5001 (Flask), 8008 (Nginx)"
$ports = @(8000, 5001, 8008)
foreach ($port in $ports) {
  $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
  if ($conns) {
    $pids = $conns.OwningProcess | Sort-Object -Unique
    foreach ($procId in $pids) {
      Write-Host (" - port {0}: PID {1} -> stopping" -f $port, $procId)
      Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
  }
}

Write-Host "[stop] 完成。"
