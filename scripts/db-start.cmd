@echo off
chcp 65001 >nul
REM Start local PostgreSQL (dev). Chinese notes: see README.md
D:\anaconda\envs\spider_env\Library\bin\pg_ctl.exe -D E:\agentlearn\pgdata -l E:\agentlearn\pgdata\postgres.log start
