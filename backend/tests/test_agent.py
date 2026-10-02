"""Agent 循环测试：用 Fake 模型（剧本）驱动，不调真 LLM —— 快、稳、可控。

这用的是概念课第 3 课的老办法：FakeLLM 照着剧本念台词。
真模型只留给演示和端到端（计划要求：普通测试用 Fake 模型）。
"""

import json

from agent import run_agent


def scripted(*outputs):
    # 做一个"按剧本念台词"的假模型
    it = iter(outputs)
    return lambda messages: next(it)


def test_success_flow():
    # 剧本：先查工单，再给最终答案 —— 成功路径
    llm = scripted(
        json.dumps({"kind": "tool_call", "name": "query_tickets", "params": {"status": "closed"}}),
        json.dumps({"kind": "final_answer", "answer": "有 1 张已关闭工单：日志采集服务重启。"}),
    )
    r = run_agent("已关闭的工单有哪些？", llm_chat=llm)
    assert r["status"] == "final_answer"
    assert len(r["steps"]) == 2
    # 调用记录要完整：工具名、参数、结果、耗时
    assert r["steps"][0]["tool"] == "query_tickets"
    assert r["steps"][0]["params"] == {"status": "closed"}
    assert r["steps"][0]["status"] == "ok"
    assert r["steps"][0]["result"]["data"]["count"] >= 1


def test_tool_error_then_give_up():
    # 剧本：调一个不存在的工具（结果 ok=false），然后放弃 —— 错误路径
    llm = scripted(
        json.dumps({"kind": "tool_call", "name": "no_such_tool", "params": {}}),
        json.dumps({"kind": "give_up", "reason": "工具不可用"}),
    )
    r = run_agent("随便问问", llm_chat=llm)
    assert r["status"] == "give_up"
    assert r["steps"][0]["status"] == "error"          # 错误被如实记录
    assert r["steps"][0]["result"]["error"]["code"] == "UNKNOWN_TOOL"


def test_empty_result_then_give_up():
    # 剧本：查到 0 条（无结果），然后放弃 —— "无结果也能结束"
    llm = scripted(
        json.dumps({"kind": "tool_call", "name": "query_tickets",
                    "params": {"keyword": "这关键字不存在"}}),
        json.dumps({"kind": "give_up", "reason": "没有找到相关工单"}),
    )
    r = run_agent("查一个不存在的关键字", llm_chat=llm)
    assert r["status"] == "give_up"
    assert r["steps"][0]["result"]["data"]["count"] == 0


def test_max_steps_stops_loop():
    # 剧本永远输出同一个工具调用 —— Agent 必须在 max_steps 处强制停下
    call = json.dumps({"kind": "tool_call", "name": "query_tickets", "params": {}})
    llm = scripted(call, call, call, call, call, call)
    r = run_agent("故意让它循环", llm_chat=llm, max_steps=3)
    assert r["status"] == "max_steps"
    assert len(r["steps"]) == 3
    assert all("elapsed_ms" in s for s in r["steps"])


def test_timeout_stops_immediately():
    # 时间预算设为 0：第一轮开始前就应该超时结束
    r = run_agent("会超时的问题", llm_chat=lambda m: "{}", deadline_seconds=0)
    assert r["status"] == "timeout"
    assert r["steps"] == []


def test_invalid_output_retries_then_gives_up():
    # 剧本全是非 JSON 输出：应记录错误、给一次改正机会，最终体面结束
    llm = scripted("这不是 JSON", "还不是", "仍然不是", "依旧不是")
    r = run_agent("测试坏输出", llm_chat=llm, max_steps=4)
    assert r["status"] == "give_up"
    assert any(s["kind"] == "invalid_output" for s in r["steps"])
    assert all(s["status"] == "error" for s in r["steps"])
