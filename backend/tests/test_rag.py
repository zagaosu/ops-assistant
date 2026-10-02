"""检索逻辑的最小业务测试。

注意：这几个测试直接读开发库（文档已入库、坐标已算好），不经过 HTTP；
每个约 1~2 秒（要调本机 Ollama 算查询的坐标）。
"""

from types import SimpleNamespace

from sqlalchemy import select

from db import SessionLocal
from models import Document
from rag import search


def _set_owner(title: str, owner: str | None) -> None:
    # 直接把某篇文档改成私有/公共，测完必须还原（finally 里做）
    with SessionLocal() as db:
        doc = db.scalar(select(Document).where(Document.title == title))
        doc.owner = owner
        db.commit()


def test_search_relevant_query():
    hits = search("冷却水温过高怎么办")
    assert len(hits) > 0
    # 最相关的一篇应该是冷却系统文档
    assert hits[0]["title"] == "冷却系统超温处置"


def test_search_irrelevant_query_returns_empty():
    # 无关问题低于阈值 -> 空列表（这就是"拒答"的防线）
    hits = search("今天天气怎么样")
    assert hits == []


def test_private_doc_invisible_to_others():
    # 文档归属 user1 之后：user1 看得到，user2 和匿名都看不到
    _set_owner("电机过载处理", "user1")
    try:
        assert any(h["title"] == "电机过载处理" for h in search("电机过载了怎么办？", user=SimpleNamespace(username="user1")))
        assert not any(h["title"] == "电机过载处理" for h in search("电机过载了怎么办？", user=SimpleNamespace(username="user2")))
        assert not any(h["title"] == "电机过载处理" for h in search("电机过载了怎么办？"))
    finally:
        _set_owner("电机过载处理", None)


def test_cache_rechecks_permission_on_hit():
    # 前提：权限只在"返回前"生效，缓存里存的是不过滤的全量结果
    user1 = SimpleNamespace(username="user1")
    assert any(h["title"] == "电机过载处理" for h in search("电机过载了怎么办？", user=user1))

    # ① 权限收紧：改成 user2 私有 -> user1 立刻看不到（不用等缓存过期）
    _set_owner("电机过载处理", "user2")
    try:
        assert not any(h["title"] == "电机过载处理" for h in search("电机过载了怎么办？", user=user1))
    finally:
        _set_owner("电机过载处理", None)

    # ② 权限恢复：改回公共 -> user1 立刻又看得到（这一条是上一版实现的漏洞）
    assert any(h["title"] == "电机过载处理" for h in search("电机过载了怎么办？", user=user1))
