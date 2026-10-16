@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PATH=%USERPROFILE%\.local\bin;%PATH%"

if not exist .venv\Scripts\python.exe (
  echo first run, installing...
  call install.bat || goto :fail
)

where uv >nul 2>nul || (
  echo uv not found, run install.bat
  goto :fail
)

set "PYTHONPATH=backend"
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 4; Start-Process 'http://127.0.0.1:7865'"
uv run --no-sync python -m somnia %*
exit /b %errorlevel%

:fail
pause
exit /b 1
