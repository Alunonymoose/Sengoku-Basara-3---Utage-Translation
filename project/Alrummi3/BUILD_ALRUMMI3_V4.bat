@echo off
setlocal
title Alrummi 3 V4 Builder
cd /d "%~dp0"
python build_alrummi3_v4.py
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)
