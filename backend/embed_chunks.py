"""Day 4：给每个分块算"语义坐标"（embedding），写入 chunks.embedding。

模型：bge-m3（通过 Ollama 本地跑，中文语义效果好）
可重复运行：重跑会覆盖旧坐标（文档重新入库后记得重跑本脚本）。
运行：D:/anaconda/envs/spider_env/python.exe -X utf8 embed_chunks.py
"""

import json
import urllib.request

from sqlalchemy import select

from db import SessionLocal
from models import Chunk

EMBED_MODEL = "bge-m3"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"


def embed_texts(texts: list[str]) -> list[list[float]]:
    # 一次把多段文本发给 Ollama，返回每段的坐标向量
    payload = {"model": EMBED_MODEL, "input": texts}
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["embeddings"]


def main():
    with SessionLocal() as db:
        chunks = db.scalars(select(Chunk).order_by(Chunk.id)).all()
        if not chunks:
            print("chunks 表是空的，先跑 ingest_docs.py")
            return

        # 12 个块一次请求全算完（比一块一块发快）
        vectors = embed_texts([c.content for c in chunks])

        for chunk, vec in zip(chunks, vectors):
            chunk.embedding = json.dumps(vec)  # 坐标存成 JSON 字符串
        db.commit()

        print(f"共写入 {len(chunks)} 个分块的坐标，每个 {len(vectors[0])} 维")


if __name__ == "__main__":
    main()
