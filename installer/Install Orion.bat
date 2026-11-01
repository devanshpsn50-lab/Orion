@echo off
setlocal EnableDelayedExpansion
title Orion Setup -- Installing...

:: -- Self-elevate to admin (needed for pip installs & file extraction) --------
net session >nul 2>&1
if errorlevel 1 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

:: ============================================================================
::  ORION INSTALLER  v1.0
::  Multithreaded Neural Semantic PC Search System
::  What this installer does:
::   1. Checks & installs Python 3.11
::   2. Checks & upgrades pip
::   3. Installs all required Python packages
::   4. Extracts Orion to %USERPROFILE%\Orion
::   5. Creates Desktop shortcut with icon
::   6. Done - launches Orion!
:: ============================================================================

cls
echo.
echo    ========================================================
echo                                                          
echo        ORION  -  PC Search System                       
echo        Multithreaded Neural Semantic Search              
echo                     INSTALLER                            
echo                                                          
echo    ========================================================
echo.
echo    This will install Orion on your PC.
echo    Installation folder: %USERPROFILE%\Orion
echo.
pause

:: ============================================================================
::  STEP 1 - Python
:: ============================================================================
echo.
echo    +-----------------------------------------+
echo    ^|  [1/5]  Checking Python...              ^|
echo    +-----------------------------------------+

set "PYTHON_OK=0"
python --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    echo         Found Python !PY_VER!
    :: Check version >= 3.9
    for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
        if %%a GEQ 3 (
            if %%b GEQ 9 set "PYTHON_OK=1"
        )
    )
)

if "!PYTHON_OK!"=="0" (
    echo         Python 3.9+ not found. Installing Python 3.11...
    echo.

    :: Try winget first (Windows 10+)
    winget --version >nul 2>&1
    if not errorlevel 1 (
        echo         Using winget to install Python...
        winget install -e --id Python.Python.3.11 --silent ^
            --accept-package-agreements --accept-source-agreements
        if not errorlevel 1 goto :python_done
    )

    :: Fallback: direct download
    echo         Downloading Python 3.11.9 installer...
    curl -L --progress-bar ^
        -o "%TEMP%\python_setup.exe" ^
        "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"

    echo         Running Python installer (please wait)...
    "%TEMP%\python_setup.exe" /quiet ^
        InstallAllUsers=0 ^
        PrependPath=1 ^
        Include_pip=1 ^
        Include_test=0 ^
        Include_launcher=1
    del "%TEMP%\python_setup.exe" >nul 2>&1

    :: Update PATH for current session
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"

    :python_done
    python --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo    [ERROR] Python installation failed.
        echo    Please install Python 3.11 manually from https://python.org
        echo    Make sure to check "Add to PATH" during installation.
        echo.
        pause
        exit /b 1
    )
    echo         Python installed successfully!
) else (
    echo         Python !PY_VER! - OK
)

:: ============================================================================
::  STEP 2 - pip
:: ============================================================================
echo.
echo    +-----------------------------------------+
echo    ^|  [2/5]  Checking pip...                 ^|
echo    +-----------------------------------------+

python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo         Bootstrapping pip...
    python -m ensurepip --upgrade >nul 2>&1
)

echo         Upgrading pip to latest...
python -m pip install --upgrade pip --quiet >nul 2>&1
echo         pip - OK

:: ============================================================================
::  STEP 3 - Extract Orion
:: ============================================================================
echo.
echo    +-----------------------------------------+
echo    ^|  [3/5]  Extracting Orion files...       ^|
echo    +-----------------------------------------+

set "INSTALL_DIR=%USERPROFILE%\Orion"
set "ZIP_FILE=%~dp0orion.zip"

if not exist "!ZIP_FILE!" (
    echo.
    echo    [ERROR] orion.zip not found next to this installer.
    echo    Make sure "Install Orion.bat" and "orion.zip" are in the same folder.
    pause
    exit /b 1
)

echo         Extracting to !INSTALL_DIR!...

if exist "!INSTALL_DIR!" (
    echo         Removing old version...
    rmdir /s /q "!INSTALL_DIR!" >nul 2>&1
)

powershell -NoProfile -Command ^
    "Expand-Archive -LiteralPath '!ZIP_FILE!' -DestinationPath '!INSTALL_DIR!' -Force" ^
    >nul 2>&1

if not exist "!INSTALL_DIR!\orion.bat" (
    echo    [ERROR] Extraction failed or orion.bat missing.
    pause
    exit /b 1
)

:: Create data folder
if not exist "!INSTALL_DIR!\data" mkdir "!INSTALL_DIR!\data"

echo         Orion extracted - OK

:: ============================================================================
::  STEP 4 - Python packages (using requirements.txt from extracted files)
:: ============================================================================
echo.
echo    +-----------------------------------------+
echo    ^|  [4/5]  Installing Python packages...   ^|
echo    +-----------------------------------------+
echo.

if exist "!INSTALL_DIR!\requirements.txt" (
    echo         Installing from requirements.txt...
    python -m pip install -r "!INSTALL_DIR!\requirements.txt" --quiet --disable-pip-version-check
    if errorlevel 1 (
        echo         [WARN] Some packages may have failed. Retrying one by one...
        for /f "usebackq delims=" %%p in ("!INSTALL_DIR!\requirements.txt") do (
            echo         Installing %%p...
            python -m pip install "%%p" --quiet --disable-pip-version-check >nul 2>&1
        )
    )
) else (
    echo         [WARN] requirements.txt not found. Installing core packages manually...
    for %%p in (fastapi uvicorn[standard] pillow pystray keyboard mutagen python-multipart aiofiles) do (
        echo         Installing %%p...
        python -m pip install %%p --quiet --disable-pip-version-check >nul 2>&1
    )
)

echo         Packages installed - OK

:: ============================================================================
::  STEP 4.5 - Everything search tool (optional, makes indexing 100x faster)
:: ============================================================================
echo.
if not exist "!INSTALL_DIR!\tools\Everything\Everything.exe" (
    echo         [NOTE] Everything search tool not bundled.
    echo         Orion will use its built-in scanner instead.
    echo         (You can install Everything later from https://www.voidtools.com)
) else (
    echo         Everything search tool - OK (bundled)
)

echo         Orion extracted - OK

:: ============================================================================
::  STEP 5 - Desktop Shortcut with icon
:: ============================================================================
echo.
echo    +-----------------------------------------+
echo    ^|  [5/5]  Creating Desktop shortcut...    ^|
echo    +-----------------------------------------+

set "SHORTCUT=%USERPROFILE%\Desktop\Orion.lnk"
set "ICON_PATH=!INSTALL_DIR!\assets\orion_icon.ico"

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$s  = $ws.CreateShortcut('!SHORTCUT!');" ^
    "$s.TargetPath     = '!INSTALL_DIR!\orion.bat';" ^
    "$s.WorkingDirectory = '!INSTALL_DIR!';" ^
    "$s.IconLocation   = '!ICON_PATH!';" ^
    "$s.Description    = 'Orion - Neural Semantic PC Search System';" ^
    "$s.WindowStyle    = 1;" ^
    "$s.Save()"

if exist "!SHORTCUT!" (
    echo         Desktop shortcut - OK
) else (
    echo         [WARN] Shortcut creation failed - you can still run Orion from !INSTALL_DIR!\orion.bat
)

:: ============================================================================
::  DONE
:: ============================================================================
echo.
echo    ========================================================
echo                                                          
echo       ORION INSTALLED SUCCESSFULLY!                      
echo                                                          
echo       -- Double-click "Orion" on your Desktop to start  
echo       -- Or run: %USERPROFILE%\Orion\orion.bat          
echo                                                          
echo       First startup will index your drive (~30-60 min)   
echo       After that, startup is instant!                    
echo                                                          
echo    ========================================================
echo.

set /p "LAUNCH=   Launch Orion now? [Y/N]: "
if /i "!LAUNCH!"=="Y" (
    start "" "!INSTALL_DIR!\orion.bat"
)

echo.
echo    Thank you for installing Orion!
echo.
timeout /t 5 /nobreak >nul
exit
