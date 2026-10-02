"""Day 14：把文档入库做成后台任务（RQ = Redis Queue）。

三个角色，缺一不可：
- 提交方：接口收到请求，把任务塞进队列，立刻返回一个 job_id（不干活）
- 队列：Redis（就是 Day 13 那个，RQ 借它存任务）
- 干活方：独立进程 `rq worker`，从队列里取任务、执行、把结果写回去

为什么要拆：入库要几十秒到几分钟，HTTP 请求干等会被网关掐断，
而且中途挂了没人知道、也没法重试。拆开后接口 100 毫秒返回，用户拿 job_id 查进度。

失败与重试：
- 任务抛异常 → RQ 记成 failed，异常信息留在 job.exc_info 里（"失败可见"）
- retry=Retry(max=2) → 自动重试，有上限（"有限重试"，不会无限刷）

入库幂等：ingest_docs 是"先删后插"，同一份文档跑几遍都只有一份分块。
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from redis import Redis
from rq import Queue, Retry
from rq.job import Job

load_dotenv(Path(__file__).parent / ".env")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = "ingest"
MAX_RETRIES = 2  # 最多再试 2 次，中间等 5 秒、15 秒

_conn = Redis.from_url(REDIS_URL)
_queue = Queue(QUEUE_NAME, connection=_conn)


def run_ingest() -> dict:
    # 后台任务本体：重新分块入库 + 重算向量
    # 函数内部才 import：worker 进程启动时不需要加载数据库和 Ollama 相关的东西
    import embed_chunks
    import ingest_docs

    ingest_docs.ingest()
    embed_chunks.main()
    return {"ok": True}


def submit_ingest() -> Job:
    # 用字符串 "jobs.run_ingest" 而不是函数对象：
    # 直接跑本文件时函数属于 __main__，worker 按名字找不到（会报
    # "Functions from the __main__ module cannot be processed by workers"）
    # job_timeout 给 15 分钟：入库要算向量，bge-m3 冷启动（模型从磁盘加载）
    # 就要 1 分钟以上，RQ 默认 180 秒不够，会把任务当"卡死"杀掉
    return _queue.enqueue("jobs.run_ingest",
                          retry=Retry(max=MAX_RETRIES, interval=[5, 15]),
                          job_timeout="15m")


def run_always_fails() -> dict:
    # 演示专用：观察"失败可见"（exc_info 留在任务上）和"有限重试"（试满就停）
    raise RuntimeError("演示用：这个任务故意失败")


def submit_failing() -> Job:
    return _queue.enqueue("jobs.run_always_fails", retry=Retry(max=MAX_RETRIES, interval=[5, 15]))


def get_status(job_id: str) -> dict:
    try:
        job = Job.fetch(job_id, connection=_conn)
    except Exception:
        return {"job_id": job_id, "status": "not_found"}

    status = job.get_status(refresh=True)
    status = str(getattr(status, "value", status))  # RQ 2.x 返回枚举，取字面值
    return {
        "job_id": job.id,
        "status": status,  # queued 排队中 / started 执行中 / finished 成功 / failed 失败
        "result": job.result if status == "finished" else None,
        "error": job.exc_info if status == "failed" else None,
        "retries_left": job.retries_left,  # 还剩几次重试机会（None = 任务没配重试）
        "queue_position": job.get_position(),
    }


if __name__ == "__main__":
    job = submit_ingest()
    print(f"已提交任务：{job.id}")
    print(f"当前状态：{job.get_status()}")
