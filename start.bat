@echo off
title Orion Search

:: ── Self-elevate to admin (one UAC prompt instead of two) ───────────────────
net session >nul 2>&1
if errorlevel 1 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

cd /d "%~dp0"

:: Check if Python packages are installed (quick check)
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo  [!] Dependencies not installed. Running setup first...
    call setup.bat
)

::  Start Everything search tool if installed (maximizes indexing speed)
if exist "tools\Everything\Everything.exe" (
    tasklist /fi "imagename eq Everything.exe" | find "Everything.exe" >nul 2>&1
    if errorlevel 1 (
        start "" /min "tools\Everything\Everything.exe"
        timeout /t 3 /nobreak >nul
    )
) else if exist "C:\Program Files\Everything\Everything.exe" (
    tasklist /fi "imagename eq Everything.exe" | find "Everything.exe" >nul 2>&1
    if errorlevel 1 (
        start "" /min "C:\Program Files\Everything\Everything.exe"
        timeout /t 2 /nobreak >nul
    )
)

:: Create required dirs
if not exist "data"   mkdir data
if not exist "assets" mkdir assets

:: Copy icon if needed
if not exist "assets\orion_icon.png" (
    if exist "..\..\.gemini\antigravity\brain\*orion_icon*.jpg" (
        copy "..\..\.gemini\antigravity\brain\*orion_icon*.jpg" "assets\orion_icon.png" >nul 2>&1
    )
)

:: Launch Orion backend (this opens the browser automatically)
echo.
echo  Launching Orion...
echo  Open your browser to: http://127.0.0.1:8472
echo  Press Ctrl+C to stop Orion.
echo.
python backend\main.py
