@echo off
setlocal
cd /d "%~dp0"
title Alrummi 3 - Install Medallion Update

echo.
echo ========================================
echo   Alrummi 3 - Medallion Update
 echo ========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found in PATH.
  echo Open PowerShell in this folder and run the normal Build_Alrummi3.ps1 once.
  pause
  exit /b 1
)

python Install_Medallion_Update.py
if errorlevel 1 (
  echo.
  echo Update failed. Nothing should have been written if the patch location was not found.
  pause
  exit /b 1
)

echo.
echo Rebuilding Alrummi3.exe...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build_Alrummi3.ps1"
if errorlevel 1 (
  echo.
  echo Source update succeeded, but the EXE build failed.
  echo You can rerun Build_Alrummi3.ps1 later.
  pause
  exit /b 1
)

echo.
echo ========================================
echo   DONE
 echo ========================================
echo New EXE:
echo   %~dp0dist\Alrummi3.exe
echo.
echo In Alrummi 3:
echo   1. Open roulette_000_ID_HQ
 echo   2. Scroll to Material and depth
 echo   3. Click Rebuild fortune medallions
 echo   4. Review candidate and confirm as normal
 echo.
pause
