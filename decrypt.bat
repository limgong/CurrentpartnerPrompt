@echo off
chcp 65001 >nul
cd /d "%~dp0"
set WECHAT_TOOL_DATA_DIR=%~dp0data
set WECHAT_TOOL_OUTPUT_DIR=%~dp0out
set PYTHONIOENCODING=utf-8

rem 
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv not found. Run setup.ps1 first.
    exit /b 1
)
if not exist "step1_decrypt.py" (
    echo [ERROR] step1_decrypt.py not found.
    exit /b 1
)

echo Requesting administrator privileges ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -FilePath '%~dp0venv\Scripts\python.exe' -ArgumentList '%~dp0step1_decrypt.py' -WorkingDirectory '%~dp0' -Verb RunAs -Wait"

echo Decrypt finished with exit code %ERRORLEVEL%
