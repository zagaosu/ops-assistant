"""Day 4：语义检索 + 带来源的回答（RAG 最小闭环）。

流程：问题 → 算坐标 → 和所有分块的坐标比相似度 → 取 top-k → 交给模型回答并注明来源
用法：D:/anaconda/envs/spider_env/python.exe -X utf8 rag.py "设备太热停不下来怎么办"
"""

import json
import math
import sys
import urllib.request

from sqlalchemy import select

from db import SessionLocal
from models import Chunk, Document
import cache

EMBED_MODEL = "bge-m3"
CHAT_MODEL = "qwen3:8b"
TOP_K = 3
# 相似度阈值：低于它视为"不相关"，宁可不答也不硬答
# （实测：无关问题最高约 0.45，相关问题 0.66 以上，中间留出安全带）
MIN_SCORE = 0.55
OLLAMA = "http://localhost:11434"


def ollama_post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        OLLAMA + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def embed_text(text: str) -> list[float]:
    data = ollama_post("/api/embed", {"model": EMBED_MODEL, "input": [text]})
    return data["embeddings"][0]


def cosine(a: list[float], b: list[float]) -> float:
    # 余弦相似度：两个坐标夹角的余弦，越接近 1 表示语义越近
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-9)


def visible_filter(username: str | None):
    # 公共文档（owner 为空）人人可见；有归属的只有本人可见
    if username is None:
        return Document.owner.is_(None)
    return (Document.owner.is_(None)) | (Document.owner == username)


def visible_only(hits: list[dict], username: str | None) -> list[dict]:
    # 返回前按"当前"权限过滤。
    # 关键：缓存里存的是不过滤的全量结果，权限只在这一步生效 ——
    # 这样权限收紧能立刻挡住，权限恢复也能立刻放行，不用等缓存过期。
    if not hits:
        return []
    ids = [h["doc_id"] for h in hits]
    with SessionLocal() as db:
        allowed = set(db.scalars(
            select(Document.id).where(Document.id.in_(ids), visible_filter(username))
        ).all())
    return [h for h in hits if h["doc_id"] in allowed]


def search(query: str, top_k: int = TOP_K, min_score: float = MIN_SCORE, user=None) -> list[dict]:
    username = getattr(user, "username", None)
    key = cache.make_key(query, top_k, min_score, username)
    cached = cache.get(key)
    if cached is not None:
        print(f"[缓存命中] {query}")
        return visible_only(cached, username)

    print(f"[缓存未命中] {query}")

    # 问题的坐标只算一次
    query_vec = embed_text(query)

    # 把库里的分块全捞出来逐个比相似度（12 个块，直接暴力比最快；块多了才需要 pgvector 那样的索引）
    # 注意这里不带权限过滤：缓存的必须是全量结果，权限在返回前才应用
    with SessionLocal() as db:
        rows = db.execute(
            select(Chunk, Document).join(Document, Chunk.document_id == Document.id)
        ).all()

    scored = []
    for chunk, doc in rows:
        if not chunk.embedding:
            continue  # 还没算坐标的块跳过
        scored.append({
            "doc_id": doc.id,
            "score": cosine(query_vec, json.loads(chunk.embedding)),
            "title": doc.title,
            "content": chunk.content,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    # 只保留分数过线的：全部不过线就返回空列表（由调用方决定怎么"体面拒答"）
    hits = [h for h in scored[:top_k] if h["score"] >= min_score]
    cache.put(key, hits)
    return visible_only(hits, username)


def answer(query: str, hits: list[dict]) -> str:
    # 把命中的纸条拼成"资料"，要求模型只依据资料回答并注明来源
    evidence = "\n\n".join(f"【{h['title']}】{h['content']}" for h in hits)
    prompt = (
        "你是设备运维助手。只能依据下面提供的资料回答问题，回答时注明依据的文档名。\n"
        "资料里没有的内容不要编造；如果资料不足以回答，就直接说明。\n\n"
        f"资料：\n{evidence}\n\n问题：{query}"
    )
    data = ollama_post("/api/chat", {
        "model": CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 400},
    })
    return data["message"]["content"]


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "设备太热停不下来怎么办"
    print(f"问题：{query}\n")

    hits = search(query)
    print(f"=== 检索到 {len(hits)} 块（top_k={TOP_K}）===")
    for h in hits:
        print(f"[{h['score']:.3f}] 《{h['title']}》 {h['content'][:40]}…")

    print("\n=== 模型回答 ===")
    print(answer(query, hits))


if __name__ == "__main__":
    main()
