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
  echo Creating a Python virtual environment (one-time setup)...
  py -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo Installing/updating dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo.
echo Starting the API at http://localhost:5111  (interactive docs at http://localhost:5111/docs)
echo Leave this window open while you use the app. Press Ctrl+C here to stop it.
echo.
python -m uvicorn app.main:app --reload --port 5111
pause
