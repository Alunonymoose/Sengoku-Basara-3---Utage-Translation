@echo off
setlocal EnableExtensions
title Install Alrummi 3 V4.1

set "TARGET=E:\Utage Patching New\Alrummi3"
set "BASE=https://raw.githubusercontent.com/Alunonymoose/Sengoku-Basara-3---Utage-Translation/alrummi3-v4-simple/project/Alrummi3"

echo.
echo ====================================================================
echo   Alrummi 3 V4.1 - validated donor + native-art texture fixer
echo ====================================================================
echo.
echo Existing V4 and older builds are left alone.
echo V4.1 will be built at:
echo   %TARGET%\dist-v41\Alrummi3_V41.exe
echo.

if not exist "%TARGET%\alrummi3_v4.py" (
    echo ERROR: Alrummi 3 V4 source was not found at:
    echo   %TARGET%
    echo.
    echo Run the V4 installer first, then run this update.
    pause
    exit /b 1
)

echo Downloading V4.1 files with cache-busting enabled...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$base='%BASE%'; $target='%TARGET%';" ^
  "$cb=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds();" ^
  "$files=@('v41_donor_validate.py','v41_image_edit.py','alrummi3_v41.py','v41_selftest.py','build_alrummi3_v41.py');" ^
  "foreach($f in $files){ Write-Host ('  ' + $f); Invoke-WebRequest -UseBasicParsing ($base+'/'+$f+'?cb='+$cb) -OutFile (Join-Path $target $f) }"
if errorlevel 1 goto :download_fail

echo.
echo Running syntax checks...
python -m py_compile "%TARGET%\v41_donor_validate.py" "%TARGET%\v41_image_edit.py" "%TARGET%\alrummi3_v41.py" "%TARGET%\v41_selftest.py" "%TARGET%\build_alrummi3_v41.py"
if errorlevel 1 goto :build_fail

echo.
echo Running V4.1 regression preflight...
cd /d "%TARGET%"
python "%TARGET%\v41_selftest.py"
if errorlevel 1 goto :build_fail

echo.
echo Building Alrummi 3 V4.1...
python "%TARGET%\build_alrummi3_v41.py"
if errorlevel 1 goto :build_fail

if not exist "%TARGET%\dist-v41\Alrummi3_V41.exe" goto :build_fail

echo.
echo ====================================================================
echo   READY
echo ====================================================================
echo.
echo Open ARC ^> select texture ^> FIX TEXTURE ^> preview ^> APPLY TO ARC
echo.
echo V4.1 now SKIPS same-Japanese / identical donor textures instead of
echo falsely calling them a successful lossless fix.
echo.
start "" "%TARGET%\dist-v41\Alrummi3_V41.exe"
exit /b 0

:download_fail
echo.
echo DOWNLOAD FAILED. Existing builds were not changed.
pause
exit /b 1

:build_fail
echo.
echo ====================================================================
echo   V4.1 BUILD / PREFLIGHT FAILED
echo ====================================================================
echo.
echo Existing builds were not replaced. Send a screenshot of the first
echo error above; the preflight should identify the broken stage.
echo.
pause
exit /b 1
