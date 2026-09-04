@echo off
title tg-montage bot - forever
cd /d C:\Users\Mventor\tg-montage
:loop
echo [%date% %time%] Starting Telegram bot ...
C:\Users\Mventor\tg-montage\.venv\Scripts\python.exe C:\Users\Mventor\tg-montage\bot.py
echo [%date% %time%] Bot exited code %errorlevel% - restarting in 5s...
timeout /t 5 /nobreak >nul
goto loop
