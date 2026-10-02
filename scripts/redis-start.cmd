@echo off
chcp 65001 >nul
REM Start Redis for the retrieval cache (Docker container ops-redis, host port 6379).
REM Requires Docker Desktop to be running.

docker start ops-redis 2>nul
if errorlevel 1 (
  echo Container not found, creating...
  docker run -d --name ops-redis -p 6379:6379 redis:7-alpine
)

echo Waiting for Redis to be ready...
:wait
docker exec ops-redis redis-cli ping 2>nul | findstr /C:"PONG" >nul
if errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)
echo Redis is ready: localhost:6379
