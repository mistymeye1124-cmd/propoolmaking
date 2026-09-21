@echo off
title Telegram Bot Health & Diagnostic Check
color 0B
echo ======================================================
echo       Running Telegram Bot Diagnostic Check...
echo ======================================================
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" check_status.py
) else (
    python check_status.py
)

echo.
echo Press any key to close this window...
pause >nul
