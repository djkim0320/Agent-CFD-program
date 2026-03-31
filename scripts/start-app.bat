@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%..\run-aero-agent.bat"
exit /b %ERRORLEVEL%
