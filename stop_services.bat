@echo off
setlocal
cd /d "%~dp0"
echo Stopping Semantic-Atlas Services...
pwsh -ExecutionPolicy Bypass -NoProfile -File ".\deploy\stop_services.ps1" %*
echo.
pause
