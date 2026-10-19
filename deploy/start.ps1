#requires -Version 5.1
[CmdletBinding()]
param(
  [ValidateSet("all", "backend", "inference", "business", "frontend")]
  [string]$Mode,

  # 模型提供方：local=本地模型，chutes=Chutes API，deepseek=DeepSeek API
  [ValidateSet("local", "chutes", "deepseek")]
  [string]$Provider,

  # 前端运行方式：static=构建产物走 Nginx，dev=Nginx 反代 Vite 开发服务器
  [ValidateSet("static", "dev")]
  [string]$FrontendRuntime,

  # 兼容旧参数：已废弃，业务后端固定使用 FastAPI 5002
  [switch]$EnableFastAPIBusiness,

  # 是否启用 FRP 内网穿透
  [switch]$Frp
)

$ErrorActionPreference = "Stop"

# 网络模式选择（本地运行 vs frp 内网穿透）
$FrpMode = $false
$FrpServerAddr = ""
$FrpToken = ""

if (-not $Frp) {
  Write-Host "请选择网络模式: 1=本地运行(默认) 2=开启frp内网穿透" -ForegroundColor Cyan
  $netChoice = Read-Host "输入编号 (默认 1)"
  if ($netChoice -eq "2") {
    $FrpMode = $true
  }
}
else {
  $FrpMode = $true
}

# .env 文件路径（用于保存/读取配置）
$Script:EnvFile = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
. "$PSScriptRoot/start_env.ps1"

# 加载 .env 文件（FRP 配置需要）
Load-EnvFile -EnvFile $Script:EnvFile

# 从环境变量读取已保存的 FRP 配置
if (-not $FrpServerAddr -and $env:FRP_SERVER_ADDR) {
  $FrpServerAddr = $env:FRP_SERVER_ADDR
}
if (-not $FrpToken -and $env:FRP_TOKEN) {
  $FrpToken = $env:FRP_TOKEN
}

# 如果启用了 frp 模式，收集配置信息
if ($FrpMode) {
  Write-Host "[start] FRP 模式已启用" -ForegroundColor Yellow
  if (-not $FrpServerAddr) {
    $FrpServerAddr = Read-Host "请输入 frp 服务器 IP 地址（留空则跳过）"
    if ($FrpServerAddr) {
      $env:FRP_SERVER_ADDR = $FrpServerAddr
      if (Save-EnvValue -EnvFile $Script:EnvFile -Name "FRP_SERVER_ADDR" -Value $FrpServerAddr) {
        Write-Host "[start] FRP Server Address saved to .env" -ForegroundColor Green
      }
    }
  }
  if (-not $FrpToken) {
    $FrpToken = Read-Host "请输入 frp 服务器密码 (token)（留空则跳过）"
    if ($FrpToken) {
      $env:FRP_TOKEN = $FrpToken
      if (Save-EnvValue -EnvFile $Script:EnvFile -Name "FRP_TOKEN" -Value $FrpToken) {
        Write-Host "[start] FRP Token saved to .env" -ForegroundColor Green
      }
    }
  }
  if (-not $FrpServerAddr -or -not $FrpToken) {
    Write-Host "[start] 错误：FRP 模式需要提供服务器 IP 和密码" -ForegroundColor Red
    exit 1
  }
}

# 启动模式选择
if (-not $Mode) {
  Write-Host "请选择启动模式: 1=all(前端+nginx+全部后端) 2=backend(两个后端) 3=inference 4=business 5=frontend" -ForegroundColor Cyan
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

if ($doFrontend -and -not $FrontendRuntime) {
  $defaultFrontendRuntime = if ($env:FRONTEND_RUNTIME) { $env:FRONTEND_RUNTIME } else { "dev" }
  Write-Host "请选择前端运行方式: 1=static(构建产物+Nginx) 2=dev(Nginx代理Vite热更新)" -ForegroundColor Cyan
  $choice = Read-Host "输入编号或模式名 (默认 $defaultFrontendRuntime)"
  switch ($choice) {
    "2" { $FrontendRuntime = "dev" }
    "dev" { $FrontendRuntime = "dev" }
    "1" { $FrontendRuntime = "static" }
    "static" { $FrontendRuntime = "static" }
    default { $FrontendRuntime = $defaultFrontendRuntime }
  }
}
elseif (-not $FrontendRuntime) {
  $FrontendRuntime = if ($env:FRONTEND_RUNTIME) { $env:FRONTEND_RUNTIME } else { "dev" }
}
$env:FRONTEND_RUNTIME = $FrontendRuntime

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

# 是否加载知识库（KB）索引，默认跳过（避免连接 HuggingFace 下载嵌入模型）
Write-Host "是否加载知识库(KB)索引? 1=no(跳过, 默认) 2=yes(需联网下载嵌入模型)" -ForegroundColor Cyan
$kbChoice = Read-Host "输入编号 (默认 1/no)"
if ($kbChoice -eq "2" -or $kbChoice -eq "yes") {
  $env:SKIP_KB_LOAD = "false"
  Write-Host "[start] KB index loading enabled." -ForegroundColor Yellow
}
else {
  $env:SKIP_KB_LOAD = "true"
  Write-Host "[start] KB index loading skipped (default)." -ForegroundColor Yellow
}

# 前端入口固定为全部模式（引导页）
$Entry = "all"
$env:FRONTEND_ENTRY = $Entry

if ($Provider -eq "chutes" -and -not $env:CHUTES_API_TOKEN) {
  Write-Host "检测到使用 chutes 模式，但未设置 CHUTES_API_TOKEN。" -ForegroundColor Yellow
  $token = Read-Host "请输入 Chutes API Token（留空则跳过）"
  if ($token) {
    $env:CHUTES_API_TOKEN = $token
    if (Save-EnvValue -EnvFile $Script:EnvFile -Name "CHUTES_API_TOKEN" -Value $token) {
      Write-Host "[start] Chutes Token saved to .env" -ForegroundColor Green
    }
  }
}

if ($Provider -eq "deepseek" -and -not $env:DEEPSEEK_API_KEY) {
  Write-Host "检测到使用 deepseek 模式，但未设置 DEEPSEEK_API_KEY。" -ForegroundColor Yellow
  $key = Read-Host "请输入 DeepSeek API Key（留空则跳过）"
  if ($key) {
    $env:DEEPSEEK_API_KEY = $key
    if (Save-EnvValue -EnvFile $Script:EnvFile -Name "DEEPSEEK_API_KEY" -Value $key) {
      Write-Host "[start] DeepSeek Key saved to .env" -ForegroundColor Green
    }
  }
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

function Resolve-NativeCommandPath {
  param([Parameter(Mandatory = $true)][string]$CommandName)

  if ([System.IO.Path]::IsPathRooted($CommandName) -or $CommandName.Contains('\') -or $CommandName.Contains('/')) {
    return $CommandName
  }

  $isWindowsHost = $env:OS -eq "Windows_NT"
  $candidates = @($CommandName)
  if ($isWindowsHost -and -not [System.IO.Path]::GetExtension($CommandName)) {
    $candidates = @("$CommandName.cmd", "$CommandName.exe", "$CommandName.bat", $CommandName)
  }

  foreach ($candidate in $candidates) {
    $command = Get-Command $candidate -CommandType Application, ExternalScript -ErrorAction SilentlyContinue |
      Select-Object -First 1
    if ($command) {
      if ($command.Source) {
        return $command.Source
      }
      if ($command.Path) {
        return $command.Path
      }
      return $command.Definition
    }
  }

  $fallback = Get-Command $CommandName -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($fallback) {
    if ($fallback.Source) {
      return $fallback.Source
    }
    if ($fallback.Path) {
      return $fallback.Path
    }
    return $fallback.Definition
  }

  return $null
}

function Invoke-RequiredNativeCommand {
  param(
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [string]$StepName
  )

  $resolvedFilePath = Resolve-NativeCommandPath -CommandName $FilePath
  if (-not $resolvedFilePath) {
    $resolvedFilePath = $FilePath
  }
  Push-Location $WorkingDirectory
  try {
    & $resolvedFilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
      throw "[start] $StepName failed with exit code $LASTEXITCODE."
    }
  }
  finally {
    Pop-Location
  }
}

function Invoke-RequiredProcess {
  param(
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [string]$StepName,
    [switch]$NoNewWindow
  )

  $processArgs = @{
    FilePath         = $FilePath
    ArgumentList     = $ArgumentList
    WorkingDirectory = $WorkingDirectory
    Wait             = $true
    PassThru         = $true
  }

  $resolvedFilePath = Resolve-NativeCommandPath -CommandName $FilePath
  if ($resolvedFilePath) {
    $processArgs.FilePath = $resolvedFilePath
  }

  if ($NoNewWindow) {
    $processArgs.NoNewWindow = $true
  }

  $process = Start-Process @processArgs
  if ($process.ExitCode -ne 0) {
    throw "[start] $StepName failed with exit code $($process.ExitCode)."
  }

  return $process
}

function Wait-DockerEngine {
  param([string]$DockerExe)

  & $DockerExe info *> $null
  if ($LASTEXITCODE -eq 0) { return }

  $context = & $DockerExe context show 2>$null
  $desktopExe = Join-Path $env:ProgramFiles "Docker/Docker/Docker Desktop.exe"
  if ($env:DOCKER_HOST -or $context -ne "desktop-linux" -or -not (Test-Path $desktopExe)) {
    throw "[start] Docker engine is unavailable. Start Docker or check its context, then retry."
  }

  Write-Host "[start] Starting Docker Desktop; waiting up to 120 seconds for the Linux engine..." -ForegroundColor Cyan
  if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $desktopExe -WindowStyle Hidden
  }
  $deadline = (Get-Date).AddSeconds(120)
  do {
    Start-Sleep -Seconds 2
    & $DockerExe info *> $null
    if ($LASTEXITCODE -eq 0) { return }
  } while ((Get-Date) -lt $deadline)

  throw "[start] Docker Desktop Linux engine did not become ready. Check Docker Desktop / WSL, then retry."
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
    if (-not $dockerCmd) {
      throw "[start] Docker is required for PostgreSQL. Install/start Docker Desktop, then retry."
    }
    Wait-DockerEngine -DockerExe $dockerCmd.Source
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
      $dockerExePath = if ($dockerCmd) { $dockerCmd.Source } else { $null }
      $selectedPort = Select-PostgresPort -DefaultPort ([int]$env:POSTGRES_PORT) -DockerExe $dockerExePath -ContainerName "semantic-atlas-postgres"
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
        Invoke-RequiredNativeCommand -FilePath $dockerCmd.Source -ArgumentList $composeArgs -WorkingDirectory $BASE_DIR -StepName "PostgreSQL docker compose"
        $containerId = & $dockerCmd.Source ps -q -f "name=semantic-atlas-postgres"
        if ($LASTEXITCODE -ne 0 -or -not $containerId) {
          throw "[start] PostgreSQL container is not running."
        }
        if (-not (Ensure-PostgresAccess -DockerExe $dockerCmd.Source -ContainerName "semantic-atlas-postgres" -DbUser $env:POSTGRES_USER -DbPassword $env:POSTGRES_PASSWORD -DbName $env:POSTGRES_DB)) {
          throw "[start] PostgreSQL user/database setup failed."
        }
      }
      catch {
        throw "[start] Failed to start PostgreSQL via docker compose: $_"
      }
    }
  }
  else {
    throw "[start] docker-compose.yml not found; cannot start PostgreSQL."
  }
}

# 前端产物目录，可通过环境变量 FRONTEND_ROOT 覆盖
$FRONTEND_ROOT = if ($env:FRONTEND_ROOT) { $env:FRONTEND_ROOT } else { Join-Path $BASE_DIR "frontend/dist" }
$FRONTEND_DEV_PORT = if ($env:FRONTEND_DEV_PORT) { [int]$env:FRONTEND_DEV_PORT } else { 5173 }

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
if ($doFrontend) { Write-Host "[start] Frontend runtime: $FrontendRuntime" }
if ($doFrontend -and $FrontendRuntime -eq "static") { Write-Host "[start] Using frontend directory: $FRONTEND_ROOT" }

if ($doFrontend) {
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
      $routerContent = $routerContent -replace "redirect: '/alpha/conflict'", "redirect: '/guide'"
      $routerContent = $routerContent -replace "redirect: '/main/login'", "redirect: '/guide'"
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
    Invoke-RequiredNativeCommand -FilePath "npm" -ArgumentList @("install") -WorkingDirectory (Get-Location).Path -StepName "npm install"
    if ($FrontendRuntime -eq "static") {
      Write-Host "[start] Building frontend (npm install & npm run build)..."
      if (Test-Path $FRONTEND_ROOT) { Remove-Item -Recurse -Force $FRONTEND_ROOT }
      Invoke-RequiredNativeCommand -FilePath "npm" -ArgumentList @("run", "build") -WorkingDirectory (Get-Location).Path -StepName "npm run build"
      $builtIndexPath = Join-Path $FRONTEND_ROOT "index.html"
      if (-not (Test-Path $builtIndexPath)) {
        throw "[start] Frontend build did not produce $builtIndexPath."
      }
    }
  }
  finally {
    Pop-Location
  }

  # 2) 生成 Nginx 配置
  $MimePath = Join-Path $BASE_DIR "deploy/mime.types"
  $NginxTemplatePath = if ($FrontendRuntime -eq "dev") {
    Join-Path $BASE_DIR "deploy/nginx_windows.dev.conf"
  }
  else {
    Join-Path $BASE_DIR "deploy/nginx_windows.conf"
  }
  $NginxTemplate = Get-Content $NginxTemplatePath -Raw
  $NginxGeneratedPath = Join-Path $BASE_DIR "deploy/nginx.generated.conf"
  $FrontForNginx = ($FRONTEND_ROOT -replace '\\', '/')
  $MimeForNginx = ($MimePath -replace '\\', '/')
  $NginxConfig = $NginxTemplate -replace '\${FRONTEND_ROOT}', $FrontForNginx
  $NginxConfig = $NginxConfig -replace '\${FRONTEND_DEV_PORT}', "$FRONTEND_DEV_PORT"
  $NginxConfig = $NginxConfig -replace '\${MIME_TYPES_PATH}', $MimeForNginx
  Set-Content -Path $NginxGeneratedPath -Value $NginxConfig -Encoding UTF8
  Write-Host "[start] Nginx config generated at $NginxGeneratedPath"
}

if ($doFrontend -and $FrontendRuntime -eq "dev") {
  $env:VITE_DEV_SERVER_HOST = "127.0.0.1"
  $env:VITE_DEV_SERVER_PORT = "$FRONTEND_DEV_PORT"
  $env:VITE_PUBLIC_PORT = "8008"
  $env:VITE_USE_POLLING = "1"
  $env:VITE_POLL_INTERVAL = "300"
  $NpmExe = Resolve-NativeCommandPath -CommandName "npm"
  if (-not $NpmExe) {
    throw "[start] npm not found."
  }
  Write-Host "[start] Starting Vite dev server ($FRONTEND_DEV_PORT) behind Nginx 8008..."
  $viteProcess = Start-Process -FilePath $NpmExe -ArgumentList @("run", "dev") -WorkingDirectory (Join-Path $BASE_DIR "frontend") -PassThru
  Start-Sleep -Seconds 3
  if ($viteProcess.HasExited) {
    throw "[start] Vite dev server exited immediately with code $($viteProcess.ExitCode)."
  }
  if (-not (Test-LocalPortOpen -Port $FRONTEND_DEV_PORT)) {
    throw "[start] Vite dev server did not open port $FRONTEND_DEV_PORT."
  }
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
    $LogDir = Join-Path $BASE_DIR "deploy/logs"
    if (-not (Test-Path $TempDir)) { New-Item -ItemType Directory -Force -Path $TempDir | Out-Null }
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

    $NginxPrefix = Join-Path $BASE_DIR "deploy"
    # Start-Process 在 Windows 上会拆分带空格的参数；这里使用单字符串并显式加引号，
    # 避免 -g 的值 "pid logs/nginx.pid;" 被拆成多个参数导致 nginx 启动失败。
    $NginxArgs = "-c `"$NginxGeneratedPath`" -p `"$NginxPrefix`" -g `"pid logs/nginx.pid;`""
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
    Invoke-RequiredProcess -FilePath $PythonExe -ArgumentList @("-m", "pip", "install", "-r", "requirements.txt") -WorkingDirectory $BASE_DIR -StepName "pip install -r requirements.txt" -NoNewWindow
  }
}

# 3.6) PostgreSQL smoke test (default when business enabled)
if ($doBusiness) {
  $TestScript = Join-Path $BASE_DIR "deploy/check_postgres.py"
  if (Test-Path $TestScript) {
    Write-Host "[start] Running PostgreSQL smoke test..." -ForegroundColor Cyan
    & $PythonExe $TestScript
    if ($LASTEXITCODE -ne 0) {
      throw "[start] PostgreSQL smoke test failed with exit code $LASTEXITCODE."
    }
  }
  else {
    throw "[start] PostgreSQL readiness script not found: $TestScript"
  }
}

# 3.7) Seed PCA infusion pump demo data for project management and analysis pages.
if ($doBusiness -and $env:SKIP_PCA_DEMO_SEED -notin @("1", "true", "True", "yes", "YES")) {
  $PcaDemoSeedScript = Join-Path $BASE_DIR "backend_business/scripts/seed_pca_demo.py"
  if (Test-Path $PcaDemoSeedScript) {
    Write-Host "[start] Seeding PCA infusion pump demo data..." -ForegroundColor Cyan
    & $PythonExe $PcaDemoSeedScript --skip-if-missing
    if ($LASTEXITCODE -ne 0) {
      throw "[start] PCA demo seed failed with exit code $LASTEXITCODE."
    }
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
  # 使用 -WorkingDirectory 确保从项目根目录启动，这样 .env 文件能被正确加载；
  # 不使用 -NoNewWindow，让每个端口在独立终端窗口运行。
  Start-Process -FilePath $PythonExe -ArgumentList $UvicornArgs -WorkingDirectory $BASE_DIR
}

# 5) 启动业务服务（FastAPI）
if ($doBusiness) {
  Write-Host "[start] Starting FastAPI business service (5002)..."
  Write-Host "[start] Working directory: $BASE_DIR"
  $UvicornArgs = @("-m", "uvicorn", "backend_business.main:app", "--host", "0.0.0.0", "--port", "5002")
  Start-Process -FilePath $PythonExe -ArgumentList $UvicornArgs -WorkingDirectory $BASE_DIR
}


Write-Host "[start] Done. Mode=$Mode; Model provider=$Provider; Entry=$Entry; FrontendRuntime=$FrontendRuntime"
$backendInfo = "FastAPI 5002"
if ($doFrontend -and $FrontendRuntime -eq "dev") {
  Write-Host "[start] Nginx 8008 -> Vite $FRONTEND_DEV_PORT (if enabled), FastAPI 8000 (if enabled), Business: $backendInfo."
}
else {
  Write-Host "[start] Nginx 8008 (if enabled), FastAPI 8000 (if enabled), Business: $backendInfo."
}
Write-Host "[start] Logs located in $LogsDir"

# 6) 启动 FRP 客户端（如果启用）
if ($FrpMode) {
  $FrpDir = Join-Path $BASE_DIR "deploy/frp"
  $FrpConfigPath = Join-Path $FrpDir "frpc.toml"
  $FrpPidPath = Join-Path $LogsDir "frpc.pid"

  Write-Host "[start] Setting up FRP client..." -ForegroundColor Cyan

  New-Item -ItemType Directory -Force -Path $FrpDir | Out-Null

  # 获取最新版本号
  $FrpVersion = "0.61.1"
  try {
    $latestRelease = Invoke-RestMethod -Uri "https://api.github.com/repos/fatedier/frp/releases/latest" -ErrorAction Stop
    if ($latestRelease.tag_name) {
      $FrpVersion = $latestRelease.tag_name
      Write-Host "[start] Latest FRP version: $FrpVersion"
    }
  }
  catch {
    Write-Host "[start] Could not fetch latest version, using default: $FrpVersion" -ForegroundColor Yellow
  }

  $FrpVersionNum = $FrpVersion -replace '^v', ''
  $FrpZipName = "frp_${FrpVersionNum}_windows_amd64.zip"
  $FrpDirName = "frp_${FrpVersionNum}_windows_amd64"
  $FrpDownloadUrl = "https://github.com/fatedier/frp/releases/download/${FrpVersion}/${FrpZipName}"
  $FrpExe = Join-Path $FrpDir "$FrpDirName/frpc.exe"

  # 检查是否需要下载
  if (-not (Test-Path $FrpExe)) {
    Write-Host "[start] Downloading FRP client from $FrpDownloadUrl..." -ForegroundColor Yellow
    $FrpZipPath = Join-Path $FrpDir $FrpZipName
    try {
      Invoke-WebRequest -Uri $FrpDownloadUrl -OutFile $FrpZipPath -UseBasicParsing
      Expand-Archive -Path $FrpZipPath -DestinationPath $FrpDir -Force
      Remove-Item -Path $FrpZipPath -Force
      Write-Host "[start] FRP client downloaded and extracted" -ForegroundColor Green
    }
    catch {
      Write-Warning "[start] Failed to download FRP client: $_"
      exit 1
    }
  }
  else {
    Write-Host "[start] FRP client already exists at $FrpExe"
  }

  # 生成 frpc.toml 配置文件
  $FrpConfigContent = @"
serverAddr = "$FrpServerAddr"
serverPort = 7000

auth.method = "token"
auth.token = "$FrpToken"

[[proxies]]
name = "nginx"
type = "tcp"
localIP = "127.0.0.1"
localPort = 8008
remotePort = 16667
"@

  Set-Content -Path $FrpConfigPath -Value $FrpConfigContent -Encoding UTF8
  Write-Host "[start] FRP config generated at $FrpConfigPath"

  # 启动 frpc
  Write-Host "[start] Starting FRP client..." -ForegroundColor Cyan
  $FrpProcess = Start-Process -FilePath $FrpExe -ArgumentList "-c", $FrpConfigPath -PassThru
  $FrpProcess.Id | Out-File -FilePath $FrpPidPath -Encoding UTF8
  Write-Host "[start] FRP client started (PID: $($FrpProcess.Id))" -ForegroundColor Green
  Write-Host "[start] Remote access: ${FrpServerAddr}:16666 -> local:8008" -ForegroundColor Green
}
