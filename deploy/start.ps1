#requires -Version 5.1
[CmdletBinding()]
param(
  [ValidateSet("all", "backend", "inference", "business", "frontend")]
  [string]$Mode,

  # 模型提供方：local=本地模型，chutes=Chutes API，deepseek=DeepSeek API（占位）
  [ValidateSet("local", "chutes", "deepseek")]
  [string]$Provider
)

$ErrorActionPreference = "Stop"

# 启动模式选择
if (-not $Mode) {
  Write-Host "请选择启动模式: 1=all(前端构建+nginx+全部后端) 2=backend(两个后端) 3=inference 4=business 5=frontend" -ForegroundColor Cyan
  $choice = Read-Host "输入编号或模式名 (默认 all)"
  switch ($choice) {
    "2" { $Mode = "backend" }
    "3" { $Mode = "inference" }
    "4" { $Mode = "business" }
    "5" { $Mode = "frontend" }
    "backend" { $Mode = "backend" }
    "inference" { $Mode = "inference" }
    "business" { $Mode = "business" }
    "frontend" { $Mode = "frontend" }
    default { $Mode = "all" }
  }
}

$doFrontend = $Mode -in @("all", "frontend")
$doNginx = $Mode -in @("all", "frontend")
$doInference = $Mode -in @("all", "backend", "inference")
$doBusiness = $Mode -in @("all", "backend", "business")

# 模型提供方选择
if (-not $Provider) {
  $defaultProvider = if ($env:MODEL_PROVIDER) { $env:MODEL_PROVIDER } else { "local" }
  Write-Host "请选择模型模式: 1=local(本地模型) 2=chutes(API) 3=deepseek(API占位)" -ForegroundColor Cyan
  $choice = Read-Host "输入编号或模式名 (默认 $defaultProvider)"
  switch ($choice) {
    "2" { $Provider = "chutes" }
    "3" { $Provider = "deepseek" }
    "local" { $Provider = "local" }
    "chutes" { $Provider = "chutes" }
    "deepseek" { $Provider = "deepseek" }
    default { $Provider = $defaultProvider }
  }
}

$env:MODEL_PROVIDER = $Provider

if ($Provider -eq "chutes" -and -not $env:CHUTES_API_TOKEN) {
  Write-Host "检测到使用 chutes 模式，但未设置 CHUTES_API_TOKEN。" -ForegroundColor Yellow
  $token = Read-Host "请输入 Chutes API Token（留空则跳过）"
  if ($token) { $env:CHUTES_API_TOKEN = $token }
}

if ($Provider -eq "deepseek" -and -not $env:DEEPSEEK_API_KEY) {
  Write-Host "检测到使用 deepseek 模式，但未设置 DEEPSEEK_API_KEY。" -ForegroundColor Yellow
  $key = Read-Host "请输入 DeepSeek API Key（留空则跳过）"
  if ($key) { $env:DEEPSEEK_API_KEY = $key }
  else { Write-Host "未输入 Key，后续调用将失败。" -ForegroundColor Yellow }
}

# 项目根目录（脚本位于 deploy/ 下）
$BASE_DIR = Split-Path -Parent $PSScriptRoot
Set-Location $BASE_DIR

# 前端产物目录，可通过环境变量 FRONTEND_ROOT 覆盖
$FRONTEND_ROOT = if ($env:FRONTEND_ROOT) { $env:FRONTEND_ROOT } else { Join-Path $BASE_DIR "frontend/dist" }

# 日志目录与 PID 路径
$LogsDir = Join-Path $BASE_DIR "deploy/logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

# 0) 先执行停止脚本清理环境
$stopScript = Join-Path $PSScriptRoot "stop_services.ps1"
if (Test-Path $stopScript) {
  Write-Host "[start] Auto-running stop_services.ps1 to clean environment..." -ForegroundColor Cyan
  & $stopScript
}

Write-Host "[start] Mode: $Mode; Model provider: $Provider"
if ($doFrontend) { Write-Host "[start] Using frontend directory: $FRONTEND_ROOT" }

if ($doFrontend) {
  # 1) 前端构建
  Write-Host "[start] Building frontend (npm install & npm run build)..."
  if (Test-Path $FRONTEND_ROOT) { Remove-Item -Recurse -Force $FRONTEND_ROOT }

  # 生成前端配置文件（保持与 Linux 脚本一致）
  @'
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
'@ | Set-Content -Path (Join-Path $BASE_DIR "frontend/tailwind.config.js") -Encoding UTF8

  @'
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
'@ | Set-Content -Path (Join-Path $BASE_DIR "frontend/postcss.config.js") -Encoding UTF8

  Push-Location (Join-Path $BASE_DIR "frontend")
  try {
    npm install
    npm run build
  }
  finally {
    Pop-Location
  }

  # 2) 生成 Nginx 配置
  $MimePath = Join-Path $BASE_DIR "deploy/mime.types"
  $NginxTemplate = Get-Content (Join-Path $BASE_DIR "deploy/nginx_windows.conf") -Raw
  $NginxGeneratedPath = Join-Path $BASE_DIR "deploy/nginx.generated.conf"
  $FrontForNginx = ($FRONTEND_ROOT -replace '\\', '/')
  $MimeForNginx = ($MimePath -replace '\\', '/')
  $NginxConfig = $NginxTemplate -replace '\${FRONTEND_ROOT}', $FrontForNginx
  $NginxConfig = $NginxConfig -replace '\${MIME_TYPES_PATH}', $MimeForNginx
  Set-Content -Path $NginxGeneratedPath -Value $NginxConfig -Encoding UTF8
  Write-Host "[start] Nginx config generated at $NginxGeneratedPath"
}

if ($doNginx -and $doFrontend) {
  # 3) 启动 / 重载 Nginx（若存在）
  $NginxVersion = "nginx-1.26.1"
  $LocalNginxPath = Join-Path $BASE_DIR "deploy/$NginxVersion/nginx.exe"
  
  # 如果本地没有，自动下载
  if (-not (Test-Path $LocalNginxPath)) {
    Write-Host "[start] Local Nginx not found. Downloading $NginxVersion..." -ForegroundColor Yellow
    $ZipPath = Join-Path $BASE_DIR "deploy/nginx.zip"
    try {
      Invoke-WebRequest -Uri "http://nginx.org/download/${NginxVersion}.zip" -OutFile $ZipPath
      Expand-Archive -Path $ZipPath -DestinationPath (Join-Path $BASE_DIR "deploy") -Force
      Remove-Item -Path $ZipPath -Force
      Write-Host "[start] Downloaded and unpacked Nginx." -ForegroundColor Green
    }
    catch {
      Write-Warning "Failed to download Nginx: $_"
    }
  }

  $NginxExe = $null

  if (Test-Path $LocalNginxPath) {
    $NginxExe = $LocalNginxPath
    Write-Host "[start] Found local Nginx: $NginxExe"
  }
  else {
    $NginxCmd = Get-Command nginx -ErrorAction SilentlyContinue
    if ($NginxCmd) { $NginxExe = $NginxCmd.Source }
  }

  if ($NginxExe) {
    # Ensure temp dir exists for Nginx
    $TempDir = Join-Path $BASE_DIR "deploy/temp"
    if (-not (Test-Path $TempDir)) { New-Item -ItemType Directory -Force -Path $TempDir | Out-Null }

    $NginxArgs = @(
      "-c", $NginxGeneratedPath,
      "-p", (Join-Path $BASE_DIR "deploy")
    )
    Write-Host "[start] Starting/reloading Nginx..."
    Start-Process -FilePath $NginxExe -ArgumentList $NginxArgs -NoNewWindow
  }
  else {
    Write-Warning "nginx not found in PATH or deploy/nginx-1.26.1; skipping reverse-proxy startup."
  }
}


# 获取当前环境 python 绝对路径，确保 Start-Process 继承正确的环境
$PythonExe = (Get-Command python).Source

# 3.5) 安装/更新依赖
if ($doInference -or $doBusiness) {
  if (Test-Path "requirements.txt") {
    Write-Host "[start] Installing/Updating Python dependencies..."
    Start-Process -FilePath $PythonExe -ArgumentList "-m pip install -r requirements.txt" -WorkingDirectory $BASE_DIR -NoNewWindow -Wait
  }
}

# 4) 启动 FastAPI 推理服务
if ($doInference) {
  $UvicornArgs = @(
    "-m", "uvicorn",
    "backend_inference.main:app",
    "--host", "0.0.0.0",
    "--port", "8000"
  )
  Write-Host "[start] Starting FastAPI inference service (8000)..."
  Write-Host "[start] Working directory: $BASE_DIR"
  # 使用 -WorkingDirectory 确保从项目根目录启动，这样 .env 文件能被正确加载
  Start-Process -FilePath $PythonExe -ArgumentList $UvicornArgs -WorkingDirectory $BASE_DIR -NoNewWindow
}

# 5) 启动 Flask 业务服务
if ($doBusiness) {
  Write-Host "[start] Starting Flask business service (5001)..."
  # 使用 -WorkingDirectory 确保从项目根目录启动
  Start-Process -FilePath $PythonExe -ArgumentList @("backend_business/app.py") -WorkingDirectory $BASE_DIR -NoNewWindow
}


Write-Host "[start] Done. Mode=$Mode; Model provider=$Provider; Nginx 8008 (if enabled), FastAPI 8000 (if enabled), Flask 5001 (if enabled)."
Write-Host "[start] Logs located in $LogsDir"
