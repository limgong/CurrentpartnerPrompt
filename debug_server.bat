@echo off
chcp 65001 >nul
cd /d "%~dp0"
set ELECTRON_RUN_AS_NODE=
set PYTHONIOENCODING=utf-8
cd persona
echo ============================================================
echo  Running backend in foreground. Errors will show below.
echo  URL: http://127.0.0.1:7860
echo  Press Ctrl+C to stop.
echo ============================================================
"..\venv\Scripts\python.exe" -u serve_api.py
echo.
echo ============================================================
echo  Backend exited with code %ERRORLEVEL%
echo ============================================================
pause
