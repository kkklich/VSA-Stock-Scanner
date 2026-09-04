@echo off
REM ===== StockPilot - launch the Python (FastAPI) backend and the React frontend =====
echo Launching the StockPilot Python backend and frontend in two separate windows...
start "StockPilot API (Python/FastAPI)" cmd /k "%~dp0run-backend-python.bat"

REM The backend window starts PostgreSQL and installs/updates dependencies
REM BEFORE the API binds port 5111, so a cold start can take a minute. The Vite
REM dev server is ready in seconds. Without this wait the browser calls an API
REM that is not listening yet and every page shows a connection error.
echo.
echo Waiting for the API on port 5111 (this can take a minute the first time)...
set "API_READY="
for /l %%i in (1,1,120) do (
  if not defined API_READY (
    netstat -ano 2>nul | findstr ":5111 " | findstr "LISTENING" >nul
    if not errorlevel 1 (
      set "API_READY=1"
    ) else (
      ping -n 2 127.0.0.1 >nul
    )
  )
)

if defined API_READY (
  echo The API is up.
) else (
  echo [WARN] The API did not start within ~2 minutes. Starting the frontend anyway.
  echo        Look at the "StockPilot API" window to see what went wrong.
)

echo.
start "StockPilot Web (frontend)" cmd /k "%~dp0run-frontend.bat"
echo Done. Two new windows should have opened.
echo   Backend  : http://localhost:5111  (docs at http://localhost:5111/docs)
echo   Frontend : http://localhost:5173
echo Close those windows to stop the app.
