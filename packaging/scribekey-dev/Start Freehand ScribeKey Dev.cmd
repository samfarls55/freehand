@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start Freehand ScribeKey Dev.ps1" %*
if errorlevel 1 pause
