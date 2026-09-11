@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  Alrummi3 v31 - Google Drive ChatGPT Factory Bridge
echo ============================================================
echo.

set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE (
    where python >nul 2>nul && set "PYEXE=python"
)
if not defined PYEXE (
    echo ERROR: Python 3 was not found on PATH.
    echo Run this from the Alrummi3 source/build workstation where v31 was built.
    pause
    exit /b 2
)

if not exist "v31_drive_bridge.py" (
    echo ERROR: v31_drive_bridge.py is missing beside this installer.
    pause
    exit /b 2
)
if not exist "install_v31_drive_bridge.py" (
    echo ERROR: install_v31_drive_bridge.py is missing beside this installer.
    pause
    exit /b 2
)

echo [1/3] Checking the current v31 GUI source without changing it...
%PYEXE% install_v31_drive_bridge.py . --dry-run
if errorlevel 1 (
    echo.
    echo Dry-run failed. Nothing has been changed.
    pause
    exit /b 3
)

echo.
echo [2/3] Installing the source-safe bridge hook...
%PYEXE% install_v31_drive_bridge.py .
if errorlevel 1 (
    echo.
    echo Install failed. The installer restores the source from backup on patch errors.
    pause
    exit /b 4
)

echo.
echo [3/3] Checking for the synced Drive factory folder...
set "FOUND_FACTORY="
for %%D in (C D E F G H I J K L M N O P Q R S T U V W X Y Z) do (
    if exist "%%D:\My Drive\Alrummi3_AI_Factory\INBOX" (
        set "FOUND_FACTORY=%%D:\My Drive\Alrummi3_AI_Factory"
        goto :factory_found
    )
)
if exist "%USERPROFILE%\Google Drive\My Drive\Alrummi3_AI_Factory\INBOX" (
    set "FOUND_FACTORY=%USERPROFILE%\Google Drive\My Drive\Alrummi3_AI_Factory"
    goto :factory_found
)
if exist "%USERPROFILE%\Google Drive\Alrummi3_AI_Factory\INBOX" (
    set "FOUND_FACTORY=%USERPROFILE%\Google Drive\Alrummi3_AI_Factory"
    goto :factory_found
)

echo.
echo Drive factory is not synced locally yet.
echo The bridge is installed, but SEND TO CHATGPT will stay in the existing v31 workflow
echo until Google Drive for desktop exposes Alrummi3_AI_Factory on this PC.
echo.
echo Once it exists, either restart Alrummi and auto-discovery will find it,
echo or set ALRUMMI3_FACTORY_ROOT to the exact synced folder.
goto :finish

:factory_found
echo Found: %FOUND_FACTORY%
setx ALRUMMI3_FACTORY_ROOT "%FOUND_FACTORY%" >nul
if errorlevel 1 (
    echo WARNING: Could not persist ALRUMMI3_FACTORY_ROOT automatically.
    echo The bridge can still auto-discover the folder on the next launch.
) else (
    echo Saved ALRUMMI3_FACTORY_ROOT for future Alrummi launches.
)

:finish
echo.
echo Installation stage complete.
echo Rebuild/relaunch the v31 executable from this updated source tree.
echo Existing ARC approval and import validation remain in force.
echo.
pause
endlocal
