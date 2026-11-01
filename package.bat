@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Orion — Build Distribution Package

:: ════════════════════════════════════════════════════════════════════════════
::  ORION PACKAGER
::  Run this script from the project root to build installer\orion.zip
::  Usage:  Double-click this file from the project root
:: ════════════════════════════════════════════════════════════════════════════

cd /d "%~dp0"

echo.
echo    Building Orion distribution package...
echo    Source:  %CD%
echo    Output:  %CD%\installer\orion.zip
echo.

:: Clean old zip
if exist "installer\orion.zip" del /f /q "installer\orion.zip"

:: Ensure installer folder exists
if not exist "installer" mkdir "installer"

:: Build zip using PowerShell (exclude dev/junk files)
powershell -NoProfile -Command ^
"$src  = '%CD%';" ^
"$dest = '%CD%\installer\orion.zip';" ^
"$exclude = @('.git','.vs','__pycache__','.gitignore','node_modules','installer','data','*.pyc','*.pyo','*.log');" ^
"$compress = Get-ChildItem -Path $src -Recurse |" ^
"  Where-Object {" ^
"    $rel = $_.FullName.Replace($src,'').TrimStart('\');" ^
"    $skip = $false;" ^
"    foreach ($ex in $exclude) {" ^
"      if ($rel -like $ex -or $rel -like ""$ex\*"") { $skip = $true; break }" ^
"    };" ^
"    -not $skip -and -not $_.PSIsContainer" ^
"  };" ^
"if (Test-Path $dest) { Remove-Item $dest -Force };" ^
"$compress | ForEach-Object {" ^
"  $entry = $_.FullName.Replace($src + '\', '');" ^
"  $_ | Add-Member -NotePropertyName RelativePath -NotePropertyValue $entry -Force" ^
"};" ^
"Add-Type -AssemblyName System.IO.Compression.FileSystem;" ^
"$zip = [System.IO.Compression.ZipFile]::Open($dest, 'Create');" ^
"foreach ($f in $compress) {" ^
"  $rel = $f.FullName.Replace($src + '\', '');" ^
"  [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $f.FullName, $rel) | Out-Null" ^
"};" ^
"$zip.Dispose();" ^
"Write-Host 'Done: ' $dest"

echo.
echo    Checking zip size...
powershell -NoProfile -Command ^
    "$f = Get-Item 'installer\orion.zip';" ^
    "Write-Host ('    orion.zip: ' + [math]::Round($f.Length/1MB, 1) + ' MB')"

echo.
echo    ══════════════════════════════════════════
echo     Distribution ready in installer\ folder:
echo     - Install Orion.bat
echo     - orion.zip
echo    ══════════════════════════════════════════
echo.
echo    Share the entire "installer" folder with users.
echo.
pause
