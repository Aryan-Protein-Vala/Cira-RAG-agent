@echo off
REM ===========================================================================
REM SSH tunnel to reach a private SAP HANA / Service Layer through a jump host.
REM
REM NO CREDENTIALS ARE STORED IN THIS FILE (the previous version did, in plain
REM text, inside a git repository). The password is asked for at run time and
REM never echoed. Endpoints come from tunnel.env next to this script, which is
REM git-ignored; copy tunnel.env.example to tunnel.env and fill it in.
REM ===========================================================================
setlocal enabledelayedexpansion

set "TUNNEL_ENV=%~dp0tunnel.env"
if not exist "%TUNNEL_ENV%" (
  echo tunnel.env not found. Copy tunnel.env.example to tunnel.env and set:
  echo   SSH_USER, SSH_HOST, HANA_HOST, HANA_PORT, SERVICE_LAYER_PORT
  exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in (`findstr /v /b /c:"#" "%TUNNEL_ENV%"`) do (
  if not "%%A"=="" set "%%A=%%B"
)

if "%HANA_PORT%"=="" set "HANA_PORT=30013"
if "%SERVICE_LAYER_PORT%"=="" set "SERVICE_LAYER_PORT=50000"

if "%SSH_USER%"=="" ( echo SSH_USER is missing in tunnel.env & exit /b 1 )
if "%SSH_HOST%"=="" ( echo SSH_HOST is missing in tunnel.env & exit /b 1 )
if "%HANA_HOST%"=="" ( echo HANA_HOST is missing in tunnel.env & exit /b 1 )

echo Forwarding local %HANA_PORT% ^& %SERVICE_LAYER_PORT% to %HANA_HOST% via %SSH_USER%@%SSH_HOST%
echo (You will be prompted for the SSH password; it is not saved anywhere.)
echo.
ssh -N -o ServerAliveInterval=30 ^
  -L %HANA_PORT%:%HANA_HOST%:%HANA_PORT% ^
  -L %SERVICE_LAYER_PORT%:%HANA_HOST%:%SERVICE_LAYER_PORT% ^
  %SSH_USER%@%SSH_HOST%
endlocal
