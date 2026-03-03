@echo off
title Google Maps Scraper Launcher
color 0B

echo ===================================================
echo   Google Maps Scraper - Initializing...
echo ===================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your system PATH!
    echo Please install Python 3 from python.org and check "Add Python to PATH".
    echo.
    pause
    exit /b
)

echo [1/4] Checking and installing Python dependencies...
pip install -r requirements.txt >nul 2>&1

echo [2/4] Ensuring Playwright browser is installed...
playwright install chromium >nul 2>&1

echo [3/4] Starting the background server...
:: Start the flask app in a minimized window
start "Maps Scraper Server" /min python app.py

echo [4/4] Waiting for server to spin up...
timeout /t 3 /nobreak >nul

echo.
echo ===================================================
echo   Done! Opening your browser to the dashboard...
echo ===================================================
start http://localhost:5000

:: Give it a second before closing the launcher
timeout /t 2 /nobreak >nul
