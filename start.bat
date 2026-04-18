@echo off
setlocal
cd /d "%~dp0"
echo Starting Semantic-Atlas Services...
pwsh -ExecutionPolicy Bypass -NoProfile -File ".\deploy\start.ps1" %*
exit /b %errorlevel%
