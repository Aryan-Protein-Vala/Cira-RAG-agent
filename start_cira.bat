@echo off
title CIRA Application Launcher
cd /d "%~dp0"

echo ========================================================
echo Launching CIRA RAG Agent (Backend + Frontend)
echo ========================================================
echo.
echo 1. Starting Backend on http://127.0.0.1:8000 in a new window...
start "CIRA Backend (Port 8000)" cmd /k "call start_backend.bat"

echo 2. Waiting 3 seconds for Backend to initialize...
timeout /t 3 /nobreak >nul

echo 3. Starting Frontend on http://localhost:3000 in a new window...
start "CIRA Frontend (Port 3000)" cmd /k "call start_frontend.bat"

echo.
echo ========================================================
echo Both services are now running!
echo Access the application at: http://localhost:3000
echo ========================================================
pause
