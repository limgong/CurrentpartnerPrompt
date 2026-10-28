@echo off
chcp 65001 >nul
cd /d "%~dp0"

if "%DEEPSEEK_API_KEY%"=="" goto local
echo [API 模式] 使用 DeepSeek API 对话
"..\venv\Scripts\python.exe" -u chat.py
goto end

:local
echo [本地模式] 没检测到 DEEPSEEK_API_KEY
echo 正在后台启动本地模型，约 30 秒...
start "" /min "..\venv\Scripts\python.exe" -u "..\serve.py"
timeout /t 35 >nul
"..\venv\Scripts\python.exe" -u chat.py --local

:end
pause
