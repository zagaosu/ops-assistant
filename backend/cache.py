"""Day 13：检索缓存 —— 同一个问题问第二遍，不重算 embedding、不查数据库。

三条纪律：
1. 缓存键要装下"所有会改变结果的输入"：问题、知识库版本、top_k、min_score。
   少一个维度，就会把不该共用的结果共用出去。
2. 知识库版本 = 分块总数 + 最新入库时间。新增、删除、重入库都会让它变
   （光看总数漏掉"改内容"，光看时间漏掉"删老文档"）。
3. 缓存是优化，不是依赖：Redis 连不上就当作未命中，检索照常走，绝不因此报错。
"""

import json
import os
from pathlib import Path

import redis
from dotenv import load_dotenv
from sqlalchemy import func, select

from db import SessionLocal
from models import Chunk

load_dotenv(Path(__file__).parent / ".env")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
TTL_SECONDS = 600  # 兜底过期：10 分钟自动作废，防止任何没想到的失效漏洞
SCHEMA_VERSION = "v2"  # 缓存值的格式变了就改这个数字，旧缓存自然作废（不用手动清 Redis）

_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def kb_version() -> str:
    # 两个数合起来才是版本：一个管"数量变了"，一个管"内容变了"
    with SessionLocal() as db:
        total, latest = db.execute(
            select(func.count(Chunk.id), func.max(Chunk.created_at))
        ).one()
    return f"{total}|{latest}"


def make_key(query: str, top_k: int, min_score: float, username: str | None = None) -> str:
    # 用户名进键：权限模型一变（文档分归属），缓存就不能跨用户共用
    # 匿名请求用 "-" 占位，和任何真实用户名都不会撞
    return (f"rag:{SCHEMA_VERSION}:user={username or '-'}|q={query}|kb={kb_version()}"
            f"|top_k={top_k}|min_score={min_score}")


def get(key: str):
    try:
        raw = _client.get(key)
    except redis.RedisError:
        return None  # Redis 挂了当未命中，主流程不受影响
    return json.loads(raw) if raw else None


def put(key: str, value) -> None:
    try:
        _client.set(key, json.dumps(value, ensure_ascii=False), ex=TTL_SECONDS)
    except redis.RedisError:
        pass
