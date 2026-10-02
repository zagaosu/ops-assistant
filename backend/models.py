"""工单表与文档表模型：一行 Python 类 = 一张数据库表。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 数据库列留 200 的余量；接口层校验也是 200（见 main.py 的 TicketCreate）
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    # 优先级：low / medium / high，不指定时按 medium
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="medium")
    owner: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Document(Base):
    # 一份入库的运维文档（source = 文件名，唯一）
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # 归属：空 = 公共文档（所有人可见）；有值 = 只有该用户可见
    owner: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 一份文档有多个分块；删文档时它的分块一起删（级联删除）
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    # 文档切出来的小块：将来检索的最小单位（Day 4 给它加向量列）
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 语义坐标（embedding）：一段文本变成的一串数字，存成 JSON 字符串
    # 开发期用 Python 算相似度；若将来上了 pgvector，这里换成 vector 类型
    embedding: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks")


class User(Base):
    # 登录账户（计划：只用两组测试账户，不做注册/找回密码）
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # 绝不存明文密码：存"盐 + 哈希"后的字符串
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    # 登录后发的令牌；重新登录会换新令牌
    api_token: Mapped[str | None] = mapped_column(String(64), unique=True)


class ChatSession(Base):
    # 一次对话（会话），属于某个用户 —— 会话历史存在数据库里，刷新不丢
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(100), nullable=False, default="新会话")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    # 会话里的一条消息（用户提问 / 助手回答）
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class TicketDraft(Base):
    # 工单草稿：Agent 或用户准备好内容后先存草稿，用户确认后才真正变成工单
    __tablename__ = "ticket_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 内容版本：确认时要带回同一版本，防止"你看过的草稿已被改过"
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    # pending 待确认 / confirmed 已确认 / cancelled 已取消
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_ticket_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
