"""Day 7：三个工具——输入校验、输出契约、错误契约。

这三个工具是 Day 8 的 Agent 将来唯一能调用的东西：
- search_docs          检索运维文档
- query_tickets        查询工单
- prepare_ticket_draft 生成工单草稿（只生成、不写库；用户确认后由应用写入）

契约（所有工具统一）：
- 输入：参数字典，用 Pydantic Schema 校验
- 输出：成功 {"ok": True, "data": ...}
        失败 {"ok": False, "error": {"code": ..., "message": ...}}
- 非法参数、未知工具都不抛异常，而是返回错误对象 —— 让 Agent 能看到错误、自己决定下一步
  （和第 4 课"空命中是数据不是异常"是同一个思想）
"""

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from db import SessionLocal
from models import Ticket
from rag import search as rag_search


def ok(data) -> dict:
    return {"ok": True, "data": data}


def err(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message}}


def validate(model: type[BaseModel], raw: dict):
    # 统一输入校验：合法返回 (模型实例, None)；非法返回 (None, 错误对象)
    try:
        return model(**raw), None
    except ValidationError as e:
        # 把 Pydantic 的报错压成一句话：哪个字段、什么问题
        first = e.errors()[0]
        field = ".".join(str(p) for p in first["loc"])
        return None, err("INVALID_PARAMS", f"参数 {field}: {first['msg']}")


# ---------------- 工具 1：检索文档 ----------------

class SearchDocsInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="检索关键词/问题")
    top_k: int = Field(3, ge=1, le=5, description="返回条数，1~5")


def search_docs(raw: dict, user=None) -> dict:
    params, e = validate(SearchDocsInput, raw)
    if e:
        return e

    hits = rag_search(params.query, top_k=params.top_k, user=user)
    return ok({
        "hits": [
            {"title": h["title"], "score": round(h["score"], 3), "content": h["content"]}
            for h in hits
        ],
        "count": len(hits),
    })


# ---------------- 工具 2：查询工单 ----------------

class QueryTicketsInput(BaseModel):
    keyword: str | None = Field(None, max_length=50, description="标题关键字，可空")
    status: str | None = Field(
        None,
        pattern="^(open|in_progress|closed|not_closed)$",
        description=(
            "按状态筛选，可空。open 待处理 / in_progress 处理中 / closed 已关闭 / "
            "not_closed 所有未关闭的（= open + in_progress）"
        ),
    )


def query_tickets(raw: dict, user=None) -> dict:
    params, e = validate(QueryTicketsInput, raw)
    if e:
        return e

    with SessionLocal() as db:
        stmt = select(Ticket).order_by(Ticket.id)
        # 用户隔离：带用户上下文时，只查这个人的工单
        if user is not None:
            stmt = stmt.where(Ticket.owner == user.username)
        if params.keyword:
            stmt = stmt.where(Ticket.title.contains(params.keyword))
        if params.status == "not_closed":
            # 别名：模型最容易犯的错是把"没关闭"当成 closed，这里让口语直译成一个合法取值
            stmt = stmt.where(Ticket.status.in_(["open", "in_progress"]))
        elif params.status:
            stmt = stmt.where(Ticket.status == params.status)
        rows = db.scalars(stmt).all()
        return ok({
            "items": [
                {"id": t.id, "title": t.title, "status": t.status, "owner": t.owner}
                for t in rows
            ],
            "count": len(rows),
        })


# ---------------- 工具 3：生成工单草稿 ----------------

class PrepareDraftInput(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=50, description="设备编号")
    symptom: str = Field(..., min_length=1, max_length=300, description="故障现象")


def prepare_ticket_draft(raw: dict, user=None) -> dict:
    params, e = validate(PrepareDraftInput, raw)
    if e:
        return e

    # 只生成草稿、不写库 —— 用户确认后由应用（Day 10）负责写入
    title = f"{params.device_id} {params.symptom}"[:200]
    return ok({
        "draft": {
            "device_id": params.device_id,
            "title": title,
            "symptom": params.symptom,
            "status": "draft",
        }
    })


# ---------------- 注册表与统一入口 ----------------

TOOL_REGISTRY = {
    "search_docs": search_docs,
    "query_tickets": query_tickets,
    "prepare_ticket_draft": prepare_ticket_draft,
}

# 工具说明书（给模型看的"菜单"）：名称、用途、参数字段都从这里自动生成
# 这样"菜单"和"后厨"永远来自同一份定义，不会脱节
TOOL_SPECS = {
    "search_docs": (SearchDocsInput, "检索运维文档，返回相关片段和来源"),
    "query_tickets": (QueryTicketsInput, "查询工单，可按关键字和状态筛选"),
    "prepare_ticket_draft": (PrepareDraftInput, "生成工单草稿（只生成，不写库）"),
}


def describe_tools() -> str:
    # 从 Pydantic Schema 自动渲染说明书（Day 8 的 Agent 会把它贴进提示词）
    lines = []
    for name, (model, desc) in TOOL_SPECS.items():
        lines.append(f"- {name}：{desc}")
        for field_name, field in model.model_fields.items():
            required = "必填" if field.is_required() else "可选"
            detail = f"；{field.description}" if field.description else ""
            lines.append(f"    参数 {field_name}（{required}{detail}）")
    return "\n".join(lines)


def execute_tool(name: str, raw_params: dict, user=None) -> dict:
    func = TOOL_REGISTRY.get(name)
    if func is None:
        return err("UNKNOWN_TOOL", f"未注册的工具: {name}（可用：{', '.join(TOOL_REGISTRY)}）")
    # user 是"工具上下文"：知道是谁在调工具，工具自己决定要不要用它做隔离
    return func(raw_params, user)
