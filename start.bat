@echo off
setlocal
cd /d "%~dp0"
echo Starting Semantic-Atlas Services...
pwsh -ExecutionPolicy Bypass -NoProfile -File ".\deploy\start.ps1" %*
set "START_EXIT_CODE=%errorlevel%"
if not "%START_EXIT_CODE%"=="0" (
  echo.
  echo [start] Startup failed with exit code %START_EXIT_CODE%. See the error above.
  pause
)
exit /b %START_EXIT_CODE%
