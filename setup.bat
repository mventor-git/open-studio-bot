@echo off
rem ============================================================
rem  Open Studio Bot — Setup Script
rem  One-click: cd, activate venv, install deps, launch
rem ============================================================
set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"
cd /d "%REPO%"

title Open Studio Bot — Setup
color 0A
echo.
echo  ================================================
echo   Open Studio Bot — First Run Setup
echo   (fork of OpenMontage, powered by opencode)
echo  ================================================
echo.

rem --- check Python ---
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
echo   Python OK

rem --- create venv if missing ---
echo [2/5] Checking virtual env...
if not exist ".venv\Scripts\python.exe" (
    echo   Creating virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create venv. Check Python installation.
        pause
        exit /b 1
    )
)
echo   Virtual env OK

rem --- activate venv ---
call .venv\Scripts\activate.bat

rem --- pip ---
echo [3/5] Checking Python packages...
set "MISSING=0"
for %%p in (telegram httpx yt_dlp playwright pyperclip PIL arabic_reshaper bidi cv2 fonttools) do (
    .venv\Scripts\python.exe -c "import %%p" >nul 2>&1
    if errorlevel 1 (
        echo   MISSING: %%p
        set "MISSING=1"
    )
)
if "%MISSING%"=="1" (
    echo.
    echo   Installing dependencies from requirements.txt...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: pip install failed. Check internet connection.
        pause
        exit /b 1
    )
    echo   Dependencies installed OK
) else (
    echo   All packages OK
)

rem --- playwright chromium ---
echo [4/5] Checking Playwright chromium...
.venv\Scripts\python.exe -c "from playwright.sync_api import sync_playwright" >nul 2>&1
if errorlevel 1 (
    echo   Installing Playwright + chromium...
    pip install playwright
    playwright install chromium
    if errorlevel 1 (
        echo ERROR: Playwright install failed.
        pause
        exit /b 1
    )
    echo   Playwright OK
) else (
    echo   Playwright OK
)

rem --- ffmpeg ---
echo [5/5] Checking ffmpeg...
if not exist "tools\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe" (
    echo   ffmpeg not found — downloading...
    if not exist "tools" mkdir tools
    powershell -Command "Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile 'tools\ffmpeg.zip'"
    if errorlevel 1 (
        echo   Could not download ffmpeg automatically.
        echo   Download manually from https://www.gyan.dev/ffmpeg/builds/
        echo   Extract to tools\ffmpeg-9.0.1-essentials_build\
        pause
    ) else (
        echo   Extracting ffmpeg...
        powershell -Command "Expand-Archive -Path tools\ffmpeg.zip -DestinationPath tools\ -Force"
        echo   ffmpeg ready
    )
) else (
    echo   ffmpeg OK
)

echo.
echo  ================================================
echo   Setup complete! Launching Open Studio Bot...
echo  ================================================
echo.
pause

rem --- launch the two services ---
start "osb-opencode" cmd /c "%REPO%\run_opencode_forever.bat"
timeout /t 3 /nobreak >nul
start "osb-bot" cmd /c "%REPO%\run_bot_forever.bat"

echo.
echo  Open Studio Bot is running!
echo  - Opencode serve (montage brain) on port 4096
echo  - Telegram bot (with T7 daily cookie check)
echo.
echo  To stop: taskkill /FI "WINDOWTITLE eq osb-*"
echo.
pause
