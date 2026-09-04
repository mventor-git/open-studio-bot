@echo off
rem Repo root = folder this script lives in (works no matter where the repo is cloned)
set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"

title osb-bot - forever (daily cookie verification runs inside bot.py every 24h, no extra process needed)
cd /d "%REPO%"
:loop
echo [%date% %time%] Starting Telegram bot (daily cookie check every %COOKIE_CHECK_HOURS%h default 24h) ...
"%REPO%\.venv\Scripts\python.exe" "%REPO%\bot.py"
echo [%date% %time%] Bot exited code %errorlevel% - restarting in 5s...
timeout /t 5 /nobreak >nul
goto loop
