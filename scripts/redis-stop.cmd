@echo off
REM Stop the Redis container (container and data are kept).
docker stop ops-redis
echo Redis stopped.
