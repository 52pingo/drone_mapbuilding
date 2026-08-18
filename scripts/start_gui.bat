@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_gui.ps1" %*
exit /b %ERRORLEVEL%
