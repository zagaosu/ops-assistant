"""Day 3：把 docs/sop 下的 Markdown 文档清洗、分块、入库。

可以重复运行：同一份文档重复导入不会产生重复分块（先删旧、再写新）。
运行：D:/anaconda/envs/spider_env/python.exe -X utf8 ingest_docs.py
"""

import re
from pathlib import Path

from sqlalchemy import func, select

from db import SessionLocal
from models import Chunk, Document

DOCS_DIR = Path(__file__).parent.parent / "docs" / "sop"

# 分块参数：每块最多多少字；相邻块重叠多少字（防止答案正好被切在块缝里）
CHUNK_SIZE = 120
CHUNK_OVERLAP = 20


def clean(text: str) -> str:
    # 清洗：去掉每行行尾空白，连续空行压成一行
    out = []
    prev_empty = False
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            if prev_empty:
                continue
            prev_empty = True
        else:
            prev_empty = False
        out.append(line)
    return "\n".join(out).strip()


def extract_title(text: str) -> str:
    # 第一行 "# 标题" 就是文档标题
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "未命名文档"


def split_chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    # 先按句子切开（在。；！？后面断句，标点留在句尾），再一句句装进不超过 size 字的块
    sentences = [s.strip() for s in re.split(r"(?<=[。；！？])", text) if s.strip()]

    chunks = []
    current = ""
    for s in sentences:
        if current and len(current) + len(s) > size:
            chunks.append(current)
            # 新块开头带上上一块的结尾一段（重叠），保证跨块的上下文也在
            current = current[-overlap:] if overlap else ""
        current += s
    if current.strip():
        chunks.append(current)
    return chunks


def ingest():
    print(f"分块参数：CHUNK_SIZE={CHUNK_SIZE} 字，OVERLAP={CHUNK_OVERLAP} 字\n")
    with SessionLocal() as db:
        for path in sorted(DOCS_DIR.glob("*.md")):
            text = clean(path.read_text(encoding="utf-8"))
            chunks = split_chunks(text)

            # 幂等：同源文档已存在就先删掉（级联删掉它的旧分块），再写新的
            old = db.scalar(select(Document).where(Document.source == path.name))
            if old is not None:
                db.delete(old)
                db.flush()

            doc = Document(source=path.name, title=extract_title(text))
            db.add(doc)
            db.flush()  # 先拿到 doc.id，分块才有得挂
            for i, c in enumerate(chunks):
                db.add(Chunk(document_id=doc.id, seq=i, content=c))
            db.commit()
            print(f"{path.name}: {len(chunks)} 块")

        n_docs = db.scalar(select(func.count()).select_from(Document))
        n_chunks = db.scalar(select(func.count()).select_from(Chunk))
        print(f"\n共 {n_docs} 份文档、{n_chunks} 个分块")


if __name__ == "__main__":
    ingest()
