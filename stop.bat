@echo off
rem CHAOS OS: stop the lab and Jenkins. Your experiment history and Jenkins data are kept.
cd /d "%~dp0"
echo Stopping the lab (including the tunnel, if share.bat was used)...
for /f %%c in ('docker ps -q --filter "label=com.docker.compose.project=chaosos"') do docker stop %%c >nul
echo Stopping Jenkins...
docker compose -f jenkins\docker-compose.yml stop
echo.
echo Stopped. Nothing was deleted. Start again with start.bat
pause
