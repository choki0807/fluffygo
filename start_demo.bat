@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "CODEX_PY=C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if exist "%CODEX_PY%" (
  set "PYTHON=%CODEX_PY%"
) else (
  set "PYTHON=python"
)

cd /d "%PROJECT_ROOT%"

echo Starting FluffyGo backend API on http://127.0.0.1:8001 ...
start "FluffyGo API" /min "%PYTHON%" api_server.py

timeout /t 2 /nobreak > nul

echo Starting FluffyGo frontend on http://127.0.0.1:8000/stitch_demo.html ...
start "FluffyGo Frontend" /min "%PYTHON%" -m http.server 8000 --bind 127.0.0.1

echo.
echo FluffyGo Demo is starting.
echo Frontend: http://127.0.0.1:8000/stitch_demo.html
echo Backend health: http://127.0.0.1:8001/api/health
echo Demo readiness: http://127.0.0.1:8001/api/demo-readiness
echo.
echo If a port is already in use, close the old python process or run restart_demo.bat if available.
echo.
pause
