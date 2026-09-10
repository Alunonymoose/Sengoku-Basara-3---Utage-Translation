@echo off
setlocal EnableExtensions
title Install Alrummi 3 V4

set "TARGET=E:\Utage Patching New\Alrummi3"
set "BASE=https://raw.githubusercontent.com/Alunonymoose/Sengoku-Basara-3---Utage-Translation/alrummi3-v4-simple/project/Alrummi3"

echo.
echo ================================================================
echo   Alrummi 3 V4 - One Button Texture Fixer
echo ================================================================
echo.
if not exist "%TARGET%\alrummi3_gui.py" (
  echo ERROR: Original Alrummi 3 source not found at %TARGET%
  pause
  exit /b 1
)

echo Downloading current V4 files...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $base='%BASE%'; $target='%TARGET%'; $cb=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds(); $files=@('v4_mttex_codec.py','v4_image_edit.py','alrummi3_v4.py','build_alrummi3_v4.py','BUILD_ALRUMMI3_V4.bat'); foreach($f in $files){ Write-Host ('  '+$f); Invoke-WebRequest -UseBasicParsing ($base+'/'+$f+'?cb='+$cb) -OutFile (Join-Path $target $f) }"
if errorlevel 1 goto :fail

python -m py_compile "%TARGET%\v4_mttex_codec.py" "%TARGET%\v4_image_edit.py" "%TARGET%\alrummi3_v4.py" "%TARGET%\build_alrummi3_v4.py"
if errorlevel 1 goto :fail

cd /d "%TARGET%"
python "%TARGET%\build_alrummi3_v4.py"
if errorlevel 1 goto :fail
if not exist "%TARGET%\dist-v4\Alrummi3_V4.exe" goto :fail
start "" "%TARGET%\dist-v4\Alrummi3_V4.exe"
exit /b 0

:fail
echo.
echo INSTALL / BUILD FAILED. Existing Alrummi builds were not replaced.
pause
exit /b 1
