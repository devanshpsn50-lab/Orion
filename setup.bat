@echo off
title Orion Setup
color 0D
echo.
echo  ============================================
echo      ORION - Search Everything, Find Anything
echo      Setup Script
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python not found.
    echo  [!] Please install Python 3.11+ from https://python.org
    echo      Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo  [OK] Python found.

:: Upgrade pip quietly
python -m pip install --upgrade pip -q

:: Install requirements
echo.
echo  [>>] Installing Python packages (this may take a minute)...
pip install -r requirements.txt -q --no-warn-script-location
if errorlevel 1 (
    echo  [!] Failed to install packages. Check your internet connection.
    pause
    exit /b 1
)
echo  [OK] Packages installed.

:: Check if Everything is installed
echo.
if exist "C:\Program Files\Everything\Everything.exe" (
    echo  [OK] Everything search tool found.
) else (
    echo  [>>] Everything search tool not found.
    echo  [>>] Downloading Everything (optional but makes indexing 100x faster)...

    :: Download Everything installer silently
    powershell -Command "& {
        try {
            Invoke-WebRequest -Uri 'https://www.voidtools.com/Everything-1.4.1.1024.x64-Setup.exe' -OutFile '%TEMP%\EverythingSetup.exe' -UseBasicParsing
            Write-Host '  [OK] Downloaded.'
        } catch {
            Write-Host '  [!] Download failed - will use built-in scanner instead.'
        }
    }"

    if exist "%TEMP%\EverythingSetup.exe" (
        echo  [>>] Installing Everything silently...
        start /wait "" "%TEMP%\EverythingSetup.exe" /S
        echo  [OK] Everything installed.
    ) else (
        echo  [!] Could not download Everything - Orion will use its built-in scanner.
        echo  [!] You can install Everything later from: https://www.voidtools.com
    )
)

:: Create data and assets directories
if not exist "data"   mkdir data
if not exist "assets" mkdir assets

:: Create desktop shortcut
echo.
echo  [>>] Creating desktop shortcut...
powershell -Command "& {
    \$ws = New-Object -ComObject WScript.Shell
    \$shortcut = \$ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Orion Search.lnk')
    \$shortcut.TargetPath  = '%~dp0start.bat'
    \$shortcut.WorkingDirectory = '%~dp0'
    \$shortcut.Description = 'Orion - Search Everything, Find Anything'
    \$shortcut.Save()
}" 2>nul
echo  [OK] Desktop shortcut created.

echo.
echo  ============================================
echo   [OK] Setup complete!
echo   Run start.bat (or double-click the desktop
echo   shortcut) to launch Orion.
echo  ============================================
echo.
pause
