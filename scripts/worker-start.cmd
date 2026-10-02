@echo off
chcp 65001 >nul
REM Start the RQ worker (background job runner). Keep this window open.
REM   --worker-class rq.worker.SimpleWorker : plain Worker needs fork(), unavailable on Windows.
REM   --with-scheduler                      : needed for retries. Without it a retried job
REM                                           sits in "scheduled" forever and never runs again.
REM Chinese notes: see README.md

cd /d E:\agentlearn\ops-assistant\backend
D:/anaconda/envs/spider_env/python.exe -X utf8 -m rq.cli worker ingest --url redis://localhost:6379/0 --worker-class rq.worker.SimpleWorker --with-scheduler
