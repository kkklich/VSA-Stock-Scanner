@echo off
REM ===== StockPilot - launch BOTH the backend and frontend in their own windows =====
echo Launching the StockPilot backend and frontend in two separate windows...
start "StockPilot API (backend)" cmd /k "%~dp0run-backend.bat"
start "StockPilot Web (frontend)" cmd /k "%~dp0run-frontend.bat"
echo Done. Two new windows should have opened. Close them to stop the app.
