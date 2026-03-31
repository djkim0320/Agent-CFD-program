@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.."
powershell -NoLogo -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start-gui.ps1"
set "EXITCODE=%ERRORLEVEL%"
popd

exit /b %EXITCODE%
