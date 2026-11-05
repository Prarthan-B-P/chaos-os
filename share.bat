@echo off
rem CHAOS OS: start everything AND share it online at a public HTTPS link (Cloudflare tunnel).
rem The link asks for a login: user "admin", password = dashboard_password in deploy\secrets.yml.
rem Stop sharing with: share.bat stop   (the lab goes back to normal local mode)
setlocal
cd /d "%~dp0"
title CHAOS OS - sharing online

if /i "%~1"=="stop" (
  powershell -NoProfile -ExecutionPolicy Bypass -File deploy\share.ps1 -Stop
  pause
  exit /b
)

if not exist deploy\secrets.yml (
  echo ERROR: deploy\secrets.yml is missing. Copy deploy\secrets.example.yml to deploy\secrets.yml and set the passwords.
  pause
  exit /b 1
)

echo [1/3] Checking Docker Desktop...
docker version >nul 2>&1
if not errorlevel 1 goto docker_ok
echo       Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set /a tries=0
:wait_docker
timeout /t 5 /nobreak >nul
docker version >nul 2>&1
if not errorlevel 1 goto docker_ok
set /a tries+=1
if %tries% lss 60 goto wait_docker
echo       ERROR: Docker Desktop did not start. Start it by hand and run this again.
pause
exit /b 1
:docker_ok

echo [2/3] Starting Jenkins (local only, never shared)...
docker compose -f jenkins\docker-compose.yml up -d >nul 2>&1

echo [3/3] Starting the lab behind the public link (login required)...
powershell -NoProfile -ExecutionPolicy Bypass -File deploy\share.ps1
echo.
echo  Jenkins (this laptop only): http://localhost:8081
echo  Stop sharing: share.bat stop      Stop everything: stop.bat
pause
