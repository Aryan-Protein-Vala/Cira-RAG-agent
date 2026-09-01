@echo off
title CIRA Frontend (Next.js - Port 3000)
cd /d "%~dp0Frontend"

echo ========================================================
echo Starting CIRA Next.js Frontend on http://localhost:3000
echo ========================================================
echo.

call npm run dev
pause
