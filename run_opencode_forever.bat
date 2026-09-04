@echo off
title tg-montage opencode serve - forever
cd /d C:\Users\Mventor\tg-montage
:loop
echo [%date% %time%] Starting opencode serve --port 4096 ...
opencode serve --port 4096
echo [%date% %time%] opencode exited code %errorlevel% - restarting in 5s...
timeout /t 5 /nobreak >nul
goto loop
