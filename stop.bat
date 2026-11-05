@echo off
rem CHAOS OS: stop the lab and Jenkins. Your experiment history and Jenkins data are kept.
cd /d "%~dp0"
echo Stopping the lab...
docker compose stop
echo Stopping Jenkins...
docker compose -f jenkins\docker-compose.yml stop
echo.
echo Stopped. Nothing was deleted. Start again with start.bat
pause
