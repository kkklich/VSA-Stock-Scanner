@echo off
REM ===== StockPilot - launch the ASP.NET Core (C#) backend API =====
cd /d "%~dp0backend"

where dotnet >nul 2>nul
if errorlevel 1 (
  echo [ERROR] The .NET SDK is not installed on this computer.
  echo Install the .NET 10 SDK from https://dotnet.microsoft.com/download/dotnet/10.0
  echo Then close this window and double-click run-backend.bat again.
  pause
  exit /b 1
)

echo.
echo Starting the API at http://localhost:5123  (OpenAPI at http://localhost:5123/openapi/v1.json)
echo Leave this window open while you use the app. Press Ctrl+C here to stop it.
echo.
dotnet run
pause
