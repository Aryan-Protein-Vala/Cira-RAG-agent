@echo off
echo ========================================================
echo Starting SSH Tunnel for SAP HANA and Service Layer...
echo ========================================================
echo.
echo This tunnel will forward local ports 30013 and 50000 
echo to the remote SAP database at 20.204.5.237 through your RDP machine.
echo.
echo It will now ask for your password. Please type:
echo CinT@2026#$%%G30DevA
echo (Note: the password will not show on screen as you type it)
echo.
ssh -L 30013:20.204.5.237:30013 -L 50000:20.204.5.237:50000 Devaditya@103.89.45.236
pause
