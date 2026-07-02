@echo off
REM ===== StockPilot - launch the Python (FastAPI) backend API =====
cd /d "%~dp0backend-python"

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python is not installed on this computer.
  echo Install Python 3.11 or newer from https://www.python.org/downloads/
  echo During install, tick "Add python.exe to PATH".
  echo Then close this window and double-click run-backend-python.bat again.
  pause
  exit /b 1
)

REM Create a local virtual environment on first run.
if not exist ".venv" (
  echo Creating a Python virtual environment ^(one-time setup^)...
  py -m venv .venv
)

call ".venv\Scripts\activate.bat"

REM ── Start PostgreSQL if it is installed via Scoop ────────────────────────────
set "PGBIN=%USERPROFILE%\scoop\apps\postgresql\current\bin"
set "PGDATA=%USERPROFILE%\scoop\apps\postgresql\current\data"

if exist "%PGBIN%\pg_ctl.exe" (

  REM Check if a server is already running and healthy.
  "%PGBIN%\pg_ctl.exe" status -D "%PGDATA%" >nul 2>nul
  if not errorlevel 1 (
    echo PostgreSQL is already running.
    goto :pg_ready
  )

  REM pg_ctl says no server, but port 5432 might still be occupied by a crashed
  REM process. Kill that process before trying to start a new one.
  for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":5432 "') do (
    if not "%%P"=="0" (
      echo Releasing stale process %%P on port 5432...
      taskkill /PID %%P /F >nul 2>nul
    )
  )

  REM Small pause to let the OS release the port.
  ping -n 3 127.0.0.1 >nul

  REM Start PostgreSQL and wait until it reports ready.
  echo Starting PostgreSQL...
  "%PGBIN%\pg_ctl.exe" start -D "%PGDATA%" -l "%PGDATA%\postgresql.log" -w
  if errorlevel 1 (
    echo [ERROR] PostgreSQL failed to start. Check the log at:
    echo         %PGDATA%\postgresql.log
    echo The API will run without a database ^(no data persistence^).
    goto :pg_skip
  )
  echo PostgreSQL started.
)

:pg_ready
:pg_skip

echo Installing/updating dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo.
echo Starting the API at http://localhost:5111  (interactive docs at http://localhost:5111/docs)
echo Leave this window open while you use the app. Press Ctrl+C here to stop it.
echo.
python -m uvicorn app.main:app --reload --port 5111
pause
