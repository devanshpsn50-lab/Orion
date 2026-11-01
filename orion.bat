@echo off
setlocal EnableDelayedExpansion
title Orion -- Neural Semantic PC Search

:: -- Self-elevate to admin (one UAC prompt instead of two) -------------------
net session >nul 2>&1
if errorlevel 1 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)


:: ================================================
::  ORION  |  Multithreaded Neural Semantic Search
::  Starting up...
:: ================================================

cd /d "%~dp0"

cls
echo.
echo     ___  ____  ___ ___  _   _
echo    / _ \^|  _ \^|_ _/ _ \^| \ ^| ^|
echo   ^| ^| ^| ^| ^|_) ^| ^| ^| ^| ^|  \^| ^|
echo   ^| ^|_^| ^|  _ ^< ^| ^| ^|_^| ^| ^|\  ^|
echo    \___/^|_^| \_\___\___/^|_^| \_^|
echo.
echo     Multithreaded Neural Semantic PC Search
echo     =========================================
echo.

:: -- Check Python -----------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Please run the Orion installer first.
    pause
    exit /b 1
)

:: -- Already running? (Orion 1 and Orion 2 share port 8472) -----------------
netstat -ano 2>nul | findstr /R /C:":8472 .*LISTENING" >nul
if not errorlevel 1 (
    echo  [!] Orion is already running on this PC.
    echo      If that is the OLD Orion, close it first:
    echo      right-click its tray icon ^(bottom-right^) - Quit, then start this again.
    echo.
    echo      Opening the running Orion in your browser...
    start "" "http://127.0.0.1:8472"
    timeout /t 8 /nobreak >nul
    exit /b 0
)

:: -- Launch Everything (background, for fast NTFS indexing) -----------------
set "EVERYTHING_EXE=%~dp0tools\Everything\Everything.exe"
if exist "%EVERYTHING_EXE%" (
    tasklist /FI "IMAGENAME eq Everything.exe" 2>nul | find /I "Everything.exe" >nul
    if errorlevel 1 (
        start "" /min "%EVERYTHING_EXE%" -startup
        timeout /t 2 /nobreak >nul
    )
)

:: -- Start Orion Backend ----------------------------------------------------
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
echo  [*] Starting Orion backend (AI models load in ~30 s)...
start "" /min python backend\main.py

echo  [*] Opening Orion in your browser...
timeout /t 2 /nobreak >nul

echo.
echo  +-----------------------------------------+
echo  ^|  Orion is running!                      ^|
echo  ^|  Open:  http://127.0.0.1:8472           ^|
echo  ^|  Hotkey: Ctrl+Space (anywhere)          ^|
echo  ^|  To stop: right-click system tray icon  ^|
echo  +-----------------------------------------+
echo.
echo  This window will close automatically.
timeout /t 4 /nobreak >nul
exit
