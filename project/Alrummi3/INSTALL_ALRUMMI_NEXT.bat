@echo off
setlocal
title Install Alrummi 3 Next

set "TARGET=E:\Utage Patching New\Alrummi3"
set "BASE=https://raw.githubusercontent.com/Alunonymoose/Sengoku-Basara-3---Utage-Translation/alrummi3-overhaul/project/Alrummi3"

echo.
echo ======================================================
echo   Alrummi 3 Next - Kuriimu2 parity overhaul
echo ======================================================
echo.
echo This installs NEXT beside the old Alrummi 3.
echo Your existing Alrummi3.exe is NOT replaced.
echo.

if not exist "%TARGET%\alrummi3_core.py" (
    echo ERROR: Alrummi3 source folder was not found at:
    echo   %TARGET%
    echo.
    pause
    exit /b 1
)

echo Downloading overhaul files...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $base='%BASE%'; $target='%TARGET%';" ^
  "$files=@('mttex_codec.py','native_texture_tools.py','alrummi3_next.py','Build_Alrummi3_Next.ps1');" ^
  "foreach($f in $files){ Write-Host ('  ' + $f); Invoke-WebRequest ($base + '/' + $f) -OutFile (Join-Path $target $f) }"

if errorlevel 1 (
    echo.
    echo DOWNLOAD FAILED. Nothing in the old build was changed.
    pause
    exit /b 1
)

echo.
echo Validating and building Alrummi 3 Next...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%TARGET%\Build_Alrummi3_Next.ps1"
if errorlevel 1 (
    echo.
    echo BUILD FAILED. Your old Alrummi3.exe is still untouched.
    echo Copy the red error text or send a screenshot.
    pause
    exit /b 1
)

echo.
echo ======================================================
echo SUCCESS
echo ======================================================
echo.
echo New test build:
echo   %TARGET%\dist-next\Alrummi3_Next.exe
echo.
echo Opening it now...
start "" "%TARGET%\dist-next\Alrummi3_Next.exe"
echo.
pause
