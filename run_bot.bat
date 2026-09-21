@echo off
title Telegram Viral Poll Bot
color 0A
echo ======================================================
echo          Starting Telegram Viral Poll Bot...
echo ======================================================
cd /d "%~dp0"

if not exist ".env" (
    echo [ERROR] .env file not found!
    echo Please configure your .env file with BOT_TOKEN first.
    pause
    exit /b
)

:: Terminate any previous hanging instances of main.py to prevent TelegramConflictError
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [INFO] Environment ready. Connecting to Telegram...
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" main.py
) else (
    python main.py
)

pause
