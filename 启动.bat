@echo off
chcp 65001 >nul
cd /d "%~dp0"
set ELECTRON_RUN_AS_NODE=
if not exist "out" mkdir "out"

if defined PERSONA_TEST (
    echo syntax-ok
    exit /b 0
)

if not exist "venv\Scripts\pythonw.exe" goto no_venv

echo Starting desktop app ...
start "" "venv\Scripts\pythonw.exe" "desktop.py"
ping -n 7 127.0.0.1 >nul 2>&1

tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /i "pythonw.exe" >nul
if errorlevel 1 goto failed

echo App window should be open. Tabs: Chat / Console.
exit /b 0

:failed
echo.
echo ============================================================
echo  App did not start. Log:
echo ============================================================
if exist "out\backend.log" type "out\backend.log"
echo.
echo Try running with console to see the error:
echo   venv\Scripts\python.exe desktop.py
echo ============================================================
pause
exit /b 1

:no_venv
echo [ERROR] venv not found. Run setup.ps1 first.
pause
exit /b 1
