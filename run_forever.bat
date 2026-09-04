@echo off
title tg-montage - forever (master)
echo Starting tg-montage forever services...
echo  - opencode serve (Claude-Free) will auto-restart
echo  - Telegram bot (videosforall19) will auto-restart (includes T7 daily cookie check every 24h via bot.py loop)
echo.

start "tg-montage-opencode" cmd /c "C:\Users\Mventor\tg-montage\run_opencode_forever.bat"
timeout /t 3 /nobreak >nul
start "tg-montage-bot" cmd /c "C:\Users\Mventor\tg-montage\run_bot_forever.bat"

echo.
echo Both windows launched. They will run FOREVER and restart on crash.
echo To stop: close both windows or run: taskkill /FI "WINDOWTITLE eq tg-montage*"
echo.
pause
