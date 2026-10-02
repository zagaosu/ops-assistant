"""Day 2：工单表 + 创建/列表接口（数据来自 PostgreSQL，不再是内存假数据）。

运行（在 backend 目录下）：
    D:/anaconda/envs/spider_env/python.exe -m uvicorn main:app --reload --port 8000
"""

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent import run_agent
from auth import current_user, login as auth_login
from db import get_db
import jobs
from models import ChatMessage, ChatSession, Ticket, TicketDraft, User
from rag import answer as rag_answer, search as rag_search

app = FastAPI(title="Ops Assistant API")


class TicketCreate(BaseModel):
    # 接口层的校验：标题必填、1~200 字；超长/缺失会被 FastAPI 拦下返回 422
    title: str = Field(..., min_length=1, max_length=200, description="工单标题")
    # 优先级可选：不传就用默认值 medium；传了必须是这三个之一（pattern 白名单）
    priority: str = Field("medium", pattern="^(low|medium|high)$", description="优先级：low/medium/high")


def ticket_to_dict(t: Ticket) -> dict:
    # 数据库行 -> 前端认识的 JSON（时间转成字符串）
    return {
        "id": t.id,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "owner": t.owner,
        "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/jobs/ingest", status_code=202)
def submit_ingest_job(user: User = Depends(current_user)):
    # 只提交、不干活：立刻返回 job_id（202 = 已受理但还没做完）
    # 真正的入库由 rq worker 那个独立进程去跑
    job = jobs.submit_ingest()
    return {"job_id": job.id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str, user: User = Depends(current_user)):
    return jobs.get_status(job_id)


@app.get("/api/tickets")
def list_tickets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    # 只列自己名下的工单（按 owner 字段过滤，工单归属隔离）
    rows = db.scalars(
        select(Ticket).where(Ticket.owner == user.username).order_by(Ticket.id)
    ).all()
    return {"items": [ticket_to_dict(t) for t in rows], "total": len(rows)}


@app.post("/api/tickets", status_code=201)
def create_ticket(payload: TicketCreate,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    # 归属由服务端决定（当前登录用户），不信任客户端传的负责人
    t = Ticket(title=payload.title, priority=payload.priority, owner=user.username)
    db.add(t)
    db.commit()
    db.refresh(t)
    return ticket_to_dict(t)


class AskRequest(BaseModel):
    # 提问接口的输入：问题必填、1~500 字
    question: str = Field(..., min_length=1, max_length=500, description="用户问题")


@app.post("/api/ask")
def ask(payload: AskRequest):
    # ① 检索：问题算坐标 -> 和所有分块比相似度 -> 取 top-3（低于阈值的丢弃）
    hits = rag_search(payload.question)
    if not hits:
        # 没有足够相关的资料：明确拒答，不硬编答案
        return {"answer": None, "sources": [], "reason": "no_relevant_docs"}

    # ② 生成：只把命中的块交给模型，要求注明来源
    text = rag_answer(payload.question, hits)

    return {
        "answer": text,
        "sources": [
            {"title": h["title"], "score": round(h["score"], 3), "snippet": h["content"][:60]}
            for h in hits
        ],
    }


# ---------------- Day 9：登录 ----------------

class LoginRequest(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=50)


@app.post("/api/login")
def login_endpoint(payload: LoginRequest, db: Session = Depends(get_db)):
    token = auth_login(db, payload.username, payload.password)
    if token is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"token": token, "username": payload.username}


# ---------------- Day 9：会话（属于当前用户，刷新不丢） ----------------

class SessionCreate(BaseModel):
    title: str = Field("新会话", max_length=100)


def session_to_dict(s: ChatSession) -> dict:
    return {"id": s.id, "title": s.title,
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M")}


@app.post("/api/sessions", status_code=201)
def create_session(payload: SessionCreate,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = ChatSession(user_id=user.id, title=payload.title)
    db.add(s)
    db.commit()
    db.refresh(s)
    return session_to_dict(s)


@app.get("/api/sessions")
def list_sessions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    # 只列自己的会话 —— 用户隔离的第一道
    rows = db.scalars(
        select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.id.desc())
    ).all()
    return {"items": [session_to_dict(s) for s in rows]}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: int,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.get(ChatSession, session_id)
    # 别人的会话一律报"不存在"（404），不泄露"存在但无权"
    if s is None or s.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = db.scalars(
        select(ChatMessage).where(ChatMessage.session_id == s.id).order_by(ChatMessage.id)
    ).all()
    return {**session_to_dict(s),
            "messages": [{"role": m.role, "content": m.content} for m in msgs]}


class AskInSession(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


@app.post("/api/sessions/{session_id}/ask")
def ask_in_session(session_id: int, payload: AskInSession,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.get(ChatSession, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 取最近 6 条历史当上下文（计划：Memory 按上下文预算加载，不塞全部历史）
    recent = db.scalars(
        select(ChatMessage).where(ChatMessage.session_id == s.id)
        .order_by(ChatMessage.id.desc()).limit(6)
    ).all()[::-1]
    history = [{"role": m.role, "content": m.content} for m in recent]

    # 先存用户提问；第一条问题顺便当会话标题
    db.add(ChatMessage(session_id=s.id, role="user", content=payload.question))
    if s.title == "新会话":
        s.title = payload.question[:30]
    db.commit()

    # 跑 Agent（Day 8 的有限步循环），把当前用户当作"工具上下文"传进去
    result = run_agent(payload.question, history=history, user=user)
    answer = result.get("answer") or result.get("reason") or "（没有输出）"

    # Agent 如果在对话里生成了工单草稿，就落库成"待确认草稿"。
    # 注意：只是草稿 —— 真正写入工单要等用户在草稿区点"确认"（计划要求"确认写入由应用处理"）
    for step in result["steps"]:
        if step.get("kind") == "tool_call" and step.get("tool") == "prepare_ticket_draft":
            data = step["result"].get("data") or {}
            if "draft" in data:
                db.add(TicketDraft(user_id=user.id,
                                   title=data["draft"]["title"],
                                   content=data["draft"]["symptom"]))

    # 再存助手回答
    db.add(ChatMessage(session_id=s.id, role="assistant", content=answer))
    db.commit()

    return {"answer": answer, "status": result["status"], "steps": result["steps"]}


# ---------------- Day 10：工单草稿与确认（事务 + 去重） ----------------

class DraftCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=1000)


def draft_to_dict(d: TicketDraft) -> dict:
    return {"id": d.id, "title": d.title, "content": d.content,
            "version": d.version, "status": d.status,
            "created_ticket_id": d.created_ticket_id,
            "created_at": d.created_at.strftime("%Y-%m-%d %H:%M")}


@app.post("/api/drafts", status_code=201)
def create_draft(payload: DraftCreate,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = TicketDraft(user_id=user.id, title=payload.title, content=payload.content)
    db.add(d)
    db.commit()
    db.refresh(d)
    return draft_to_dict(d)


@app.get("/api/drafts")
def list_drafts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(TicketDraft).where(TicketDraft.user_id == user.id).order_by(TicketDraft.id.desc())
    ).all()
    return {"items": [draft_to_dict(d) for d in rows]}


class DraftConfirm(BaseModel):
    version: int


@app.post("/api/drafts/{draft_id}/confirm")
def confirm_draft(draft_id: int, payload: DraftConfirm,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = db.get(TicketDraft, draft_id)
    if d is None or d.user_id != user.id:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 去重/幂等：已确认过的草稿，直接返回当时创建的工单，绝不写第二张
    if d.status == "confirmed":
        t = db.get(Ticket, d.created_ticket_id)
        return {"already_confirmed": True, "ticket": ticket_to_dict(t)}

    if d.status != "pending":
        raise HTTPException(status_code=409, detail="草稿已取消，不能确认")

    # 版本校验：确认时要带回你看到的那一版，防止"你确认的是旧内容"
    if payload.version != d.version:
        raise HTTPException(status_code=409, detail="内容版本不一致，请刷新后重新确认")

    # 事务：创建工单 + 标记草稿，同一次 commit 一起生效（要么都成功，要么都不发生）
    t = Ticket(title=d.title, owner=user.username)
    db.add(t)
    db.flush()  # 先拿到工单 id
    d.status = "confirmed"
    d.created_ticket_id = t.id
    db.commit()
    db.refresh(t)
    return {"already_confirmed": False, "ticket": ticket_to_dict(t)}


@app.post("/api/drafts/{draft_id}/cancel")
def cancel_draft(draft_id: int,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = db.get(TicketDraft, draft_id)
    if d is None or d.user_id != user.id:
        raise HTTPException(status_code=404, detail="草稿不存在")
    if d.status != "pending":
        raise HTTPException(status_code=409, detail="只有待确认的草稿能取消")
    d.status = "cancelled"
    db.commit()
    return draft_to_dict(d)
