@echo off
title tg-montage bot - forever (T7: daily cookie verification runs inside bot.py every 24h, no extra process needed)
cd /d C:\Users\Mventor\tg-montage
:loop
echo [%date% %time%] Starting Telegram bot (T7 daily cookie check every %COOKIE_CHECK_HOURS%h default 24h) ...
C:\Users\Mventor\tg-montage\.venv\Scripts\python.exe C:\Users\Mventor\tg-montage\bot.py
echo [%date% %time%] Bot exited code %errorlevel% - restarting in 5s...
timeout /t 5 /nobreak >nul
goto loop
