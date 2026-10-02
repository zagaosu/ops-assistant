@echo off
REM Stop local PostgreSQL (dev).
D:\anaconda\envs\spider_env\Library\bin\pg_ctl.exe -D E:\agentlearn\pgdata stop
