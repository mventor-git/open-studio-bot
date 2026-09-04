@echo off
rem Repo root = folder this script lives in
set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"

title osb-opencode serve - forever
cd /d "%REPO%"
:loop
echo [%date% %time%] Starting opencode serve --port 4096 ...
opencode serve --port 4096
echo [%date% %time%] opencode exited code %errorlevel% - restarting in 5s...
timeout /t 5 /nobreak >nul
goto loop
