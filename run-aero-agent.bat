@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "SCRIPTS_DIR=%ROOT_DIR%scripts\"

if not exist "%SCRIPTS_DIR%start-api.bat" (
  echo [ERROR] Missing launcher: %SCRIPTS_DIR%start-api.bat
  exit /b 1
)

if not exist "%SCRIPTS_DIR%start-gui.bat" (
  echo [ERROR] Missing launcher: %SCRIPTS_DIR%start-gui.bat
  exit /b 1
)

echo [Aero Agent] Launching API window...
start "Aero Agent API" cmd /k "\"%SCRIPTS_DIR%start-api.bat\""

timeout /t 2 /nobreak >nul

echo [Aero Agent] Launching GUI window...
start "Aero Agent GUI" cmd /k "\"%SCRIPTS_DIR%start-gui.bat\""

echo [Aero Agent] API and GUI launchers were started in separate windows.
exit /b 0
