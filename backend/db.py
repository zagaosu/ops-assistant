"""数据库连接：从 .env 读 DATABASE_URL，建连接池和会话工厂。

为什么密钥放 .env 而不是写在代码里：代码会进仓库，.env 不会（见 .gitignore）。
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# 读 backend/.env（和本文件同目录）
load_dotenv(Path(__file__).parent / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]

# engine = 连接池：程序启动时建好，之后每个请求复用它
engine = create_engine(DATABASE_URL)

# SessionLocal = 会话工厂：每个请求调一次，开一个独立的数据库会话
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    # 所有表模型的基类，迁移工具靠它找到全部表
    pass


def get_db():
    # FastAPI 依赖：每个请求开一个数据库会话，请求处理完自动关闭
    # 放在 db.py 里统一提供 —— 接口、鉴权、测试都走这一根管道
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
