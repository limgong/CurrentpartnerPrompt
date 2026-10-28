@echo off
chcp 65001 >nul
cd /d "%~dp0"
set ELECTRON_RUN_AS_NODE=
if not exist "out" mkdir "out"

if defined PERSONA_TEST (
    echo syntax-ok
    exit /b 0
)

echo Starting Edge app-mode window ...
start "" /min "venv\Scripts\pythonw.exe" "desktop.py"
timeout /t 8 >nul
echo Started. Window title: PersonaChat / URL: http://127.0.0.1:7860
echo Closing the window keeps the server running.
echo To stop the server, use the "Quit" button in the console page.
pause
