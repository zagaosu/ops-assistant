"""工具契约测试：合法参数行为正确、非法参数返回错误对象（不崩溃）。

注意：search_docs 会调本机 Ollama（约 1~2 秒）；其余走本地数据库/纯逻辑。
"""

from tools import execute_tool


def test_search_docs_ok():
    r = execute_tool("search_docs", {"query": "冷却水温过高怎么办"})
    assert r["ok"] is True
    assert r["data"]["count"] > 0
    assert r["data"]["hits"][0]["title"] == "冷却系统超温处置"


def test_search_docs_invalid_params():
    # 空 query
    r = execute_tool("search_docs", {"query": ""})
    assert r["ok"] is False
    assert r["error"]["code"] == "INVALID_PARAMS"

    # top_k 超出范围
    r2 = execute_tool("search_docs", {"query": "温度", "top_k": 99})
    assert r2["ok"] is False


def test_query_tickets_keyword_filter():
    r = execute_tool("query_tickets", {"keyword": "冷却"})
    assert r["ok"] is True
    # 返回的每一条标题里都应该含关键字
    assert all("冷却" in t["title"] for t in r["data"]["items"])


def test_query_tickets_status_filter():
    # 合法状态：只回 closed 的
    r = execute_tool("query_tickets", {"status": "closed"})
    assert r["ok"] is True
    assert all(t["status"] == "closed" for t in r["data"]["items"])

    # 非法状态值（不在三选一里）：被输入校验拦下
    r2 = execute_tool("query_tickets", {"status": "done"})
    assert r2["ok"] is False
    assert r2["error"]["code"] == "INVALID_PARAMS"


def test_prepare_ticket_draft_ok():
    r = execute_tool("prepare_ticket_draft", {"device_id": "pump-03", "symptom": "水温 95 度"})
    assert r["ok"] is True
    assert r["data"]["draft"]["status"] == "draft"
    assert "pump-03" in r["data"]["draft"]["title"]


def test_prepare_ticket_draft_missing_param():
    # 缺 symptom，应被拦下
    r = execute_tool("prepare_ticket_draft", {"device_id": "pump-03"})
    assert r["ok"] is False
    assert r["error"]["code"] == "INVALID_PARAMS"


def test_unknown_tool():
    r = execute_tool("delete_everything", {})
    assert r["ok"] is False
    assert r["error"]["code"] == "UNKNOWN_TOOL"
