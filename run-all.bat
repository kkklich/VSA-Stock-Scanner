@echo off
REM ===== StockPilot - launch the Python (FastAPI) backend and the React frontend =====
echo Launching the StockPilot Python backend and frontend in two separate windows...
start "StockPilot API (Python/FastAPI)" cmd /k "%~dp0run-backend-python.bat"
start "StockPilot Web (frontend)" cmd /k "%~dp0run-frontend.bat"
echo Done. Two new windows should have opened.
echo   Backend  : http://localhost:5111  (docs at http://localhost:5111/docs)
echo   Frontend : http://localhost:5173
echo Close those windows to stop the app.
