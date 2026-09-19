@echo off
rem ---------------------------------------------------------------------------
rem  Double-click entry point for the case dashboard.
rem
rem  A .html file cannot start a process, so the actual launcher has to be a
rem  batch file; launcher.html is only the "re-open it while it is already
rem  running" shortcut.  This script just runs run.py --prod from the repo root,
rem  which serves caseDashboard/web/dist and opens the browser by itself.
rem
rem  Double-clicking twice is safe: run.py recognises the instance it already
rem  started and just hands back its URL instead of reporting the port as taken.
rem
rem  Output is English, like the dashboard itself.
rem ---------------------------------------------------------------------------
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo.
    echo   Python 3 not found. Install Python 3.10 or newer from
    echo   https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo.
echo   Starting the case parameter dashboard ...
echo   http://127.0.0.1:8765/  -- your browser will open by itself.
echo   Close this window to stop the server.
echo.

%PY% caseDashboard\run.py --prod
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
    echo   Startup failed - exit code %RC%.
    echo   If the port is held by another program, end that process and retry.
) else (
    echo   Dashboard stopped.
)

pause
endlocal
