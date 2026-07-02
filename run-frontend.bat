@echo off
REM ===== StockPilot - launch the React (Vite) frontend =====
cd /d "%~dp0frontend"

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js is not installed on this computer.
  echo Install the LTS version from https://nodejs.org/en/download
  echo Then close this window and double-click run-frontend.bat again.
  pause
  exit /b 1
)

if not exist node_modules (
  echo Installing frontend dependencies ^(this only happens the first time^)...
  call npm install
  if errorlevel 1 (
    echo.
    echo [ERROR] npm install failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
)

echo.
echo Starting the dev server at http://localhost:5173
echo Open that address in your browser. Leave this window open while you use
echo the app. Press Ctrl+C here to stop it.
echo.
call npm run dev
pause
