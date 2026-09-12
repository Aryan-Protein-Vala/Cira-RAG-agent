@echo off
title CIRA Backend (FastAPI - Port 8000)
cd /d "%~dp0Backend"

echo ========================================================
echo Starting CIRA FastAPI Backend on http://127.0.0.1:8000
echo ========================================================
echo.

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
    echo [OK] Virtual environment activated.
) else (
    echo [INFO] No local venv found, using system Python.
)

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
