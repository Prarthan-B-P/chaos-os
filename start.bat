@echo off
rem CHAOS OS: start everything (Docker Desktop, the lab, Jenkins) and open the dashboards.
rem Double-click this file, or run it from a terminal in the project folder.
setlocal
cd /d "%~dp0"
title CHAOS OS - starting

echo [1/4] Checking Docker Desktop...
docker version >nul 2>&1
if not errorlevel 1 goto docker_ok
echo       Docker is not running - starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set /a tries=0
:wait_docker
timeout /t 5 /nobreak >nul
docker version >nul 2>&1
if not errorlevel 1 goto docker_ok
set /a tries+=1
if %tries% lss 60 goto wait_docker
echo       ERROR: Docker Desktop did not start within 5 minutes. Start it by hand and run this again.
pause
exit /b 1
:docker_ok
echo       Docker is running.

echo [2/4] Starting the lab (first time: builds images, takes several minutes)...
docker compose up -d --build --wait
if errorlevel 1 (
  echo       ERROR: the lab did not become healthy. See: docker compose ps
  pause
  exit /b 1
)

echo [3/4] Starting Jenkins...
docker compose -f jenkins\docker-compose.yml up -d >nul 2>&1

echo [4/4] Opening the dashboards...
start "" http://localhost:8090
start "" http://localhost:8090/#/oncall
start "" "http://localhost:3000/d/chaos-os-service-health"
start "" http://localhost:8081/job/chaos-os-ci/

echo.
echo  CHAOS OS is running.
echo    Evidence dashboard  http://localhost:8090
echo    On-call console     http://localhost:8090/#/oncall
echo    Grafana             http://localhost:3000   (admin / admin)
echo    Jenkins             http://localhost:8081
echo    Prometheus          http://localhost:9090
echo    Alertmanager        http://localhost:9093
echo    Shop                http://localhost:8080
echo.
echo  To stop everything: double-click stop.bat
pause
