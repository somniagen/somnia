@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "INTERACTIVE="
echo %cmdcmdline% | find /i "%~nx0" >nul && set "INTERACTIVE=1"

set "DRY="
if "%~1"=="" goto :start
if /i "%~1"=="--check" (
  set "DRY=1"
  goto :start
)
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="-h" goto :usage
echo unknown option: %~1
goto :usage_fail

:start
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set "UV_PYTHON_PREFERENCE=only-managed"

echo Somnia install
if defined DRY echo [check] dry run, nothing will be changed

where uv >nul 2>nul || (
  if defined DRY (
    echo [check] uv missing, would install it from astral.sh
  ) else (
    echo installing uv...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    where uv >nul 2>nul || goto :fail_uv
  )
)

if defined DRY (
  echo [check] would run: uv python install 3.12
  echo [check] would run: uv sync
) else (
  echo installing python 3.12...
  uv python install 3.12 || goto :fail
  echo installing python packages...
  uv sync || goto :fail
)

set "NEED_WEB="
if not exist web\dist\index.html set "NEED_WEB=1"
if not defined NEED_WEB (
  powershell -NoProfile -Command "if ((Get-ChildItem web/src,web/index.html,web/package.json -Recurse -File | Where-Object { $_.LastWriteTime -gt (Get-Item web/dist/index.html).LastWriteTime }).Count -gt 0) { exit 1 } else { exit 0 }"
  if errorlevel 1 set "NEED_WEB=1"
)

if defined NEED_WEB (
  if defined DRY (
    echo [check] would build the frontend in web
  ) else (
    where npm >nul 2>nul || goto :no_npm
    echo building frontend...
    pushd web
    call npm ci || call npm install || goto :fail_web
    call npm run build || goto :fail_web
    popd
  )
) else (
  echo frontend up to date
)

if exist scripts\fetch_tags.py (
  if defined DRY (
    echo [check] would run: scripts\fetch_tags.py
  ) else (
    echo prefetching small assets...
    .venv\Scripts\python.exe scripts\fetch_tags.py || echo warning: asset prefetch failed, continuing
  )
)

echo.
if defined DRY (
  echo [check] done, nothing was changed
) else (
  echo Done. Start Somnia with run.bat
)
goto :ok

:fail_uv
echo could not install uv, see https://docs.astral.sh/uv/
goto :fail

:no_npm
echo npm not found, install Node.js LTS: winget install OpenJS.NodeJS.LTS
goto :fail

:fail_web
popd
echo frontend build failed, see messages above
goto :fail

:fail
echo install failed, see messages above
if defined INTERACTIVE pause
exit /b 1

:ok
if defined INTERACTIVE if not defined DRY pause
exit /b 0

:usage_fail
call :usage
if defined INTERACTIVE pause
exit /b 1

:usage
echo usage: install.bat [--check]
echo   --check  show what would be done, change nothing
exit /b 0
