#requires -Version 5.1
[CmdletBinding()]
param(
  [ValidateSet("all", "backend", "inference", "business", "frontend")]
  [string]$Mode,

  # 模型提供方：local=本地模型，chutes=Chutes API，deepseek=DeepSeek API
  [ValidateSet("local", "chutes", "deepseek")]
  [string]$Provider,

  # 前端入口：alpha=测试页面，main=正式页面，all=全部模式(引导页)
  [ValidateSet("alpha", "main", "all")]
  [string]$Entry,

  # 是否启动 FastAPI 业务后端 (与 Flask 并行运行，使用 /api/v2/ 前缀)
  [switch]$EnableFastAPIBusiness
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
  $defaultProvider = if ($env:MODEL_PROVIDER) { $env:MODEL_PROVIDER } else { "deepseek" }
  Write-Host "请选择模型模式: 1=local(本地模型) 2=chutes(API) 3=deepseek" -ForegroundColor Cyan
  $choice = Read-Host "输入编号或模式名 (默认 $defaultProvider)"
  switch ($choice) {
    "1" { $Provider = "local" }
    "2" { $Provider = "chutes" }
    "3" { $Provider = "deepseek" }
    "local" { $Provider = "local" }
    "chutes" { $Provider = "chutes" }
    "deepseek" { $Provider = "deepseek" }
    default { $Provider = $defaultProvider }
  }
}

$env:MODEL_PROVIDER = $Provider

# 是否加载模型选择 (默认不加载)
Write-Host "是否加载本地模型权重? 1=no(跳过, 启动快) 2=yes(加载, 需GPU/大内存)" -ForegroundColor Cyan
$loadChoice = Read-Host "输入编号 (默认 1/no)"
if ($loadChoice -eq "2" -or $loadChoice -eq "yes") {
  $env:SKIP_MODEL_LOAD = "false"
  Write-Host "[start] Model loading enabled." -ForegroundColor Yellow
}
else {
  $env:SKIP_MODEL_LOAD = "true"
  Write-Host "[start] Model loading skipped (default)." -ForegroundColor Yellow
}

# 前端入口选择
if (-not $Entry) {
  $defaultEntry = if ($env:FRONTEND_ENTRY) { $env:FRONTEND_ENTRY } else { "all" }
  Write-Host "请选择前端入口: 1=main(正式页面) 2=alpha(测试页面) 3=all(全部模式+引导页)" -ForegroundColor Cyan
  $choice = Read-Host "输入编号或模式名 (默认 $defaultEntry)"
  switch ($choice) {
    "1" { $Entry = "main" }
    "2" { $Entry = "alpha" }
    "3" { $Entry = "all" }
    "main" { $Entry = "main" }
    "alpha" { $Entry = "alpha" }
    "all" { $Entry = "all" }
    default { $Entry = $defaultEntry }
  }
}

$env:FRONTEND_ENTRY = $Entry

# 是否启动 FastAPI 业务后端
if (-not $EnableFastAPIBusiness) {
  Write-Host "是否启动 FastAPI 业务后端 (/api/v2/)? 1=yes(默认, 与Flask并行) 2=no" -ForegroundColor Cyan
  $choice = Read-Host "输入编号 (默认 1/yes)"
  if ($choice -eq "2" -or $choice -eq "no") {
    $EnableFastAPIBusiness = $false
  }
  else {
    $EnableFastAPIBusiness = $true
    Write-Host "[start] FastAPI business backend will be enabled." -ForegroundColor Yellow
  }
}

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

# Conda env setup for Python services
$CondaEnv = "semantic-Atlas"
$CondaPythonVersion = "3.12"

function Initialize-Conda {
  $condaExe = $env:CONDA_EXE
  if (-not $condaExe) {
    $condaCmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($condaCmd) { $condaExe = $condaCmd.Source }
  }

  if (-not $condaExe) {
    return $null
  }

  $hook = & $condaExe "shell.powershell" "hook" 2>$null | Out-String
  if (-not $hook) {
    return $null
  }

  Invoke-Expression $hook
  return $condaExe
}

$condaExe = Initialize-Conda
if ($condaExe) {
  $envExists = $false
  try {
    $envJson = conda env list --json | ConvertFrom-Json
    if ($envJson -and $envJson.envs) {
      $envExists = $envJson.envs |
      ForEach-Object { Split-Path $_ -Leaf } |
      Where-Object { $_ -eq $CondaEnv } |
      Select-Object -First 1
    }
  }
  catch {
    Write-Warning "[start] Failed to list conda envs: $_"
  }

  if (-not $envExists) {
    Write-Host "[start] Conda env '$CondaEnv' not found. Creating..." -ForegroundColor Yellow
    conda create -n $CondaEnv python=$CondaPythonVersion -y
  }

  Write-Host "[start] Activating conda env '$CondaEnv'..."
  conda activate $CondaEnv
}
else {
  Write-Warning "[start] Conda not found or hook failed; skipping conda activation."
}

function Escape-PostgresLiteral {
  param([string]$Value)
  if ($null -eq $Value) { return "" }
  return $Value.Replace("'", "''")
}

function Invoke-PostgresSql {
  param(
    [string]$DockerExe,
    [string]$ContainerName,
    [string]$Sql,
    [string[]]$Users,
    [string]$Database,
    [string]$Password
  )

  $lastOutput = $null
  foreach ($user in $Users) {
    if (-not $user) { continue }
    $args = @("exec", $ContainerName, "psql", "-v", "ON_ERROR_STOP=1", "-U", $user, "-d", $Database, "-c", $Sql)
    $lastOutput = & $DockerExe @args 2>&1
    if ($LASTEXITCODE -eq 0) {
      return @{ Success = $true; Output = $lastOutput }
    }

    if ($Password) {
      $args = @("exec", "-e", "PGPASSWORD=$Password", $ContainerName, "psql", "-v", "ON_ERROR_STOP=1", "-U", $user, "-d", $Database, "-c", $Sql)
      $lastOutput = & $DockerExe @args 2>&1
      if ($LASTEXITCODE -eq 0) {
        return @{ Success = $true; Output = $lastOutput }
      }
    }
  }

  return @{ Success = $false; Output = $lastOutput }
}

function Ensure-PostgresAccess {
  param(
    [string]$DockerExe,
    [string]$ContainerName,
    [string]$DbUser,
    [string]$DbPassword,
    [string]$DbName
  )

  $dbUserEsc = Escape-PostgresLiteral $DbUser
  $dbPasswordEsc = Escape-PostgresLiteral $DbPassword
  $dbNameEsc = Escape-PostgresLiteral $DbName

  $sqlTemplate = @'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '__DB_USER__') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '__DB_USER__', '__DB_PASS__');
  ELSE
    EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', '__DB_USER__', '__DB_PASS__');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '__DB_NAME__') THEN
    EXECUTE format('CREATE DATABASE %I OWNER %I', '__DB_NAME__', '__DB_USER__');
  END IF;
END
$$;
'@

  $sql = $sqlTemplate.Replace("__DB_USER__", $dbUserEsc).Replace("__DB_PASS__", $dbPasswordEsc).Replace("__DB_NAME__", $dbNameEsc)
  $adminUsers = @("postgres", $DbUser) | Where-Object { $_ } | Select-Object -Unique

  for ($i = 1; $i -le 8; $i++) {
    $result = Invoke-PostgresSql -DockerExe $DockerExe -ContainerName $ContainerName -Sql $sql -Users $adminUsers -Database "postgres" -Password $DbPassword
    if ($result.Success) {
      Write-Host "[start] PostgreSQL role/database ensured." -ForegroundColor Green
      return $true
    }
    Write-Host "[start] PostgreSQL not ready, retry $i/8..." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
  }

  Write-Warning "[start] Failed to ensure PostgreSQL user/database in container."
  return $false
}

function Test-LocalPortOpen {
  param([int]$Port)
  try {
    $result = Test-NetConnection -ComputerName "127.0.0.1" -Port $Port -WarningAction SilentlyContinue
    return [bool]$result.TcpTestSucceeded
  }
  catch {
    return $false
  }
}

function Test-PostgresPortConflict {
  param([int]$Port)
  if (-not (Test-LocalPortOpen -Port $Port)) {
    return $false
  }
  try {
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
    foreach ($listener in $listeners) {
      try {
        $proc = Get-Process -Id $listener.OwningProcess -ErrorAction Stop
        if ($proc.ProcessName -match "postgres") {
          return $true
        }
      }
      catch {
        continue
      }
    }
  }
  catch {
    return $true
  }
  return $true
}

function Get-ContainerHostPort {
  param(
    [string]$DockerExe,
    [string]$ContainerName,
    [string]$ContainerPort
  )
  try {
    $format = '{{(index (index .NetworkSettings.Ports "' + $ContainerPort + '") 0).HostPort}}'
    $hostPort = & $DockerExe inspect -f $format $ContainerName 2>$null
    if ($LASTEXITCODE -eq 0 -and $hostPort -and $hostPort -ne "<no value>") {
      return $hostPort
    }
  }
  catch {
    return $null
  }
  return $null
}

function Select-PostgresPort {
  param(
    [int]$DefaultPort,
    [string]$DockerExe,
    [string]$ContainerName
  )

  if ($DockerExe) {
    $existingPort = Get-ContainerHostPort -DockerExe $DockerExe -ContainerName $ContainerName -ContainerPort "5432/tcp"
    if ($existingPort) {
      return [int]$existingPort
    }
  }

  if (-not (Test-LocalPortOpen -Port $DefaultPort)) {
    return $DefaultPort
  }

  for ($p = $DefaultPort + 1; $p -le ($DefaultPort + 10); $p++) {
    if (-not (Test-LocalPortOpen -Port $p)) {
      return $p
    }
  }

  return $DefaultPort
}

# Start PostgreSQL via Docker Compose (if business backend enabled)
if ($doBusiness) {
  if (-not $env:POSTGRES_HOST -or $env:POSTGRES_HOST -in @("localhost", "::1")) {
    $env:POSTGRES_HOST = "127.0.0.1"
  }
  $portExplicit = [bool]$env:POSTGRES_PORT
  if (-not $env:POSTGRES_PORT) { $env:POSTGRES_PORT = "5433" }
  if (-not $env:POSTGRES_PORT_LOCK) { $env:POSTGRES_PORT_LOCK = "1" }
  if (-not $env:POSTGRES_USER) { $env:POSTGRES_USER = "semantic" }
  if (-not $env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD = "semantic_dev" }
  if (-not $env:POSTGRES_DB) { $env:POSTGRES_DB = "semantic_atlas" }

  $composeFile = Join-Path $BASE_DIR "docker-compose.yml"
  if (Test-Path $composeFile) {
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    $dockerComposeCmd = Get-Command docker-compose -ErrorAction SilentlyContinue
    $portLocked = $env:POSTGRES_PORT_LOCK -in @("1", "true", "True")
    $needsOverride = $false
    if (-not $portLocked) {
      if (-not $portExplicit) {
        $needsOverride = $true
      }
      elseif ($env:POSTGRES_PORT -eq "5432" -and (Test-PostgresPortConflict -Port ([int]$env:POSTGRES_PORT))) {
        $needsOverride = $true
      }
    }
    if ($needsOverride) {
      $selectedPort = Select-PostgresPort -DefaultPort ([int]$env:POSTGRES_PORT) -DockerExe ($dockerCmd ? $dockerCmd.Source : $null) -ContainerName "semantic-atlas-postgres"
      if ($selectedPort -ne [int]$env:POSTGRES_PORT) {
        Write-Warning "[start] Port $($env:POSTGRES_PORT) is in use. Switching PostgreSQL host port to $selectedPort."
        $env:POSTGRES_PORT = "$selectedPort"
      }
    }
    $forceRecreate = $false
    if ($dockerCmd) {
      $existingContainer = & $dockerCmd.Source ps -a -q -f "name=semantic-atlas-postgres"
      if ($existingContainer) {
        $publishedPort = Get-ContainerHostPort -DockerExe $dockerCmd.Source -ContainerName "semantic-atlas-postgres" -ContainerPort "5432/tcp"
        if (-not $publishedPort) {
          Write-Warning "[start] PostgreSQL container has no published host port. Forcing recreate."
          $forceRecreate = $true
        }
        elseif ([int]$publishedPort -ne [int]$env:POSTGRES_PORT) {
          Write-Warning "[start] PostgreSQL container is bound to host port $publishedPort, expected $($env:POSTGRES_PORT). Forcing recreate."
          $forceRecreate = $true
        }
      }
    }
    if ($dockerCmd) {
      try {
        Write-Host "[start] Starting PostgreSQL via docker compose..." -ForegroundColor Cyan
        $composeArgs = @("compose", "-f", $composeFile, "up", "-d")
        if ($forceRecreate) { $composeArgs += "--force-recreate" }
        $composeArgs += "postgres", "adminer"
        Start-Process -FilePath $dockerCmd.Source -ArgumentList $composeArgs -NoNewWindow -Wait
        $containerId = & $dockerCmd.Source ps -q -f "name=semantic-atlas-postgres"
        if ($containerId) {
          Ensure-PostgresAccess -DockerExe $dockerCmd.Source -ContainerName "semantic-atlas-postgres" -DbUser $env:POSTGRES_USER -DbPassword $env:POSTGRES_PASSWORD -DbName $env:POSTGRES_DB | Out-Null
        }
      }
      catch {
        Write-Warning "[start] Failed to start PostgreSQL via docker compose: $_"
      }
    }
    elseif ($dockerComposeCmd) {
      try {
        Write-Host "[start] Starting PostgreSQL via docker-compose..." -ForegroundColor Cyan
        $composeArgs = @("-f", $composeFile, "up", "-d")
        if ($forceRecreate) { $composeArgs += "--force-recreate" }
        $composeArgs += "postgres", "adminer"
        Start-Process -FilePath $dockerComposeCmd.Source -ArgumentList $composeArgs -NoNewWindow -Wait
        if ($dockerCmd) {
          $containerId = & $dockerCmd.Source ps -q -f "name=semantic-atlas-postgres"
          if ($containerId) {
            Ensure-PostgresAccess -DockerExe $dockerCmd.Source -ContainerName "semantic-atlas-postgres" -DbUser $env:POSTGRES_USER -DbPassword $env:POSTGRES_PASSWORD -DbName $env:POSTGRES_DB | Out-Null
          }
        }
      }
      catch {
        Write-Warning "[start] Failed to start PostgreSQL via docker-compose: $_"
      }
    }
    else {
      Write-Warning "[start] Docker not found; skipping PostgreSQL startup."
    }
  }
  else {
    Write-Warning "[start] docker-compose.yml not found; skipping PostgreSQL startup."
  }
}

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

  # 根据入口选择修改路由默认重定向
  $routerPath = Join-Path $BASE_DIR "frontend/src/router/index.js"
  if (Test-Path $routerPath) {
    $routerContent = Get-Content $routerPath -Raw -Encoding UTF8
    if ($Entry -eq "alpha") {
      $routerContent = $routerContent -replace "redirect: '/main/login'", "redirect: '/alpha/conflict'"
      $routerContent = $routerContent -replace "redirect: '/guide'", "redirect: '/alpha/conflict'"
      Write-Host "[start] Frontend entry set to: alpha (测试页面)" -ForegroundColor Yellow
    }
    elseif ($Entry -eq "all") {
      $routerContent = $routerContent -replace "redirect: '/main/login'", "redirect: '/guide'"
      $routerContent = $routerContent -replace "redirect: '/alpha/conflict'", "redirect: '/guide'"
      Write-Host "[start] Frontend entry set to: all (全部模式+引导页)" -ForegroundColor Yellow
    }
    else {
      $routerContent = $routerContent -replace "redirect: '/alpha/conflict'", "redirect: '/main/login'"
      $routerContent = $routerContent -replace "redirect: '/guide'", "redirect: '/main/login'"
      Write-Host "[start] Frontend entry set to: main (正式页面)" -ForegroundColor Yellow
    }
    Set-Content -Path $routerPath -Value $routerContent -Encoding UTF8 -NoNewline
  }

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
      "-p", (Join-Path $BASE_DIR "deploy"),
      "-g", "pid logs/nginx.pid;"
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

# Ensure a compatible Python version for psycopg2 wheels
try {
  $pyVersionText = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
  if ($pyVersionText -match '^(\d+)\.(\d+)$') {
    $pyMajor = [int]$matches[1]
    $pyMinor = [int]$matches[2]
    if ($pyMajor -gt 3 -or ($pyMajor -eq 3 -and $pyMinor -ge 13)) {
      throw "[start] Detected Python $pyMajor.$pyMinor which is not supported by psycopg2-binary. Please use Python $CondaPythonVersion."
    }
  }
}
catch {
  throw $_
}

# 3.5) 安装/更新依赖
if ($doInference -or $doBusiness) {
  if (Test-Path "requirements.txt") {
    Write-Host "[start] Installing/Updating Python dependencies..."
    Start-Process -FilePath $PythonExe -ArgumentList "-m pip install -r requirements.txt" -WorkingDirectory $BASE_DIR -NoNewWindow -Wait
  }
}

# 3.6) PostgreSQL smoke test (default when business enabled)
if ($doBusiness) {
  $TestScript = Join-Path $BASE_DIR "tests/fixtures/test_postgres.py"
  if (Test-Path $TestScript) {
    Write-Host "[start] Running PostgreSQL smoke test..." -ForegroundColor Cyan
    & $PythonExe $TestScript
    if ($LASTEXITCODE -ne 0) {
      throw "[start] PostgreSQL smoke test failed with exit code $LASTEXITCODE."
    }
  }
  else {
    Write-Warning "[start] PostgreSQL test script not found; skipping smoke test."
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

# 5) 启动业务服务 (Flask 默认，FastAPI 可选并行)
if ($doBusiness) {
  # Flask (主业务后端)
  Write-Host "[start] Starting Flask business service (5001)..."
  Start-Process -FilePath $PythonExe -ArgumentList @("backend_business/app.py") -WorkingDirectory $BASE_DIR -NoNewWindow

  # FastAPI 业务后端 (可选，使用 /api/v2/ 前缀)
  if ($EnableFastAPIBusiness) {
    Write-Host "[start] Starting FastAPI business service (5002) with /api/v2/ prefix..."
    Write-Host "[start] Working directory: $BASE_DIR"
    $UvicornArgs = @("-m", "uvicorn", "backend_business.main:app", "--host", "0.0.0.0", "--port", "5002")
    Start-Process -FilePath $PythonExe -ArgumentList $UvicornArgs -WorkingDirectory $BASE_DIR -NoNewWindow
  }
}


Write-Host "[start] Done. Mode=$Mode; Model provider=$Provider; Entry=$Entry"
$backendInfo = if ($EnableFastAPIBusiness) { "Flask 5001 + FastAPI 5002 (/api/v2/)" } else { "Flask 5001" }
Write-Host "[start] Nginx 8008 (if enabled), FastAPI 8000 (if enabled), Business: $backendInfo."
Write-Host "[start] Logs located in $LogsDir"