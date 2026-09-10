@echo off
setlocal EnableExtensions
title Install Alrummi 3 Hybrid

set "TARGET=E:\Utage Patching New\Alrummi3"
set "BASE=https://raw.githubusercontent.com/Alunonymoose/Sengoku-Basara-3---Utage-Translation/alrummi3-hybrid/project/Alrummi3"

echo.
echo ============================================================
echo   Alrummi 3 Hybrid - corrected codec + original features
echo ============================================================
echo.
echo This DOES NOT delete or replace your current Alrummi3.exe.
echo It builds a separate test EXE at:
echo   %TARGET%\dist-hybrid\Alrummi3_Hybrid.exe
echo.

if not exist "%TARGET%\alrummi3_gui.py" (
    echo ERROR: The original Alrummi 3 source was not found at:
    echo   %TARGET%
    echo.
    pause
    exit /b 1
)
if not exist "%TARGET%\bcn.py" (
    echo ERROR: bcn.py is missing from the Alrummi 3 folder.
    pause
    exit /b 1
)

echo Downloading Hybrid overlay files...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $base='%BASE%'; $target='%TARGET%';" ^
  "$files=@('mttex_codec.py','openai_image_edit.py','alrummi3_hybrid.py','Build_Alrummi3_Hybrid.ps1');" ^
  "foreach($f in $files){ Write-Host ('  ' + $f); Invoke-WebRequest ($base + '/' + $f) -OutFile (Join-Path $target $f) }"
if errorlevel 1 goto :fail

echo.
echo Building and running regression checks...
powershell -NoProfile -ExecutionPolicy Bypass -File "%TARGET%\Build_Alrummi3_Hybrid.ps1"
if errorlevel 1 goto :fail

if not exist "%TARGET%\dist-hybrid\Alrummi3_Hybrid.exe" goto :fail

echo.
echo ============================================================
echo   SUCCESS
echo ============================================================
echo.
echo Launching the Hybrid build now.
start "" "%TARGET%\dist-hybrid\Alrummi3_Hybrid.exe"
exit /b 0

:fail
echo.
echo ============================================================
echo   INSTALL / BUILD FAILED
echo ============================================================
echo.
echo Your existing Alrummi3.exe was not replaced.
echo Send me a screenshot of the error above.
echo.
pause
exit /b 1
