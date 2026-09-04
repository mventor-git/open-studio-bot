@echo off
rem Run from anywhere: repo root = folder this script lives in
set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"

title Open Studio Bot - forever (master)
echo Starting Open Studio Bot forever services...
echo  - opencode serve (montage brain) will auto-restart
echo  - Telegram bot will auto-restart (daily cookie check every 24h via bot.py loop)
echo.

start "osb-opencode" cmd /c "%REPO%\run_opencode_forever.bat"
timeout /t 3 /nobreak >nul
start "osb-bot" cmd /c "%REPO%\run_bot_forever.bat"

echo.
echo Both windows launched. They will run FOREVER and restart on crash.
echo To stop: close both windows or run: taskkill /FI "WINDOWTITLE eq osb-*"
echo.
pause
