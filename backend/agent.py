"""Day 8：有限步 Agent —— 模型决定 → 执行工具 → 观察结果 → 继续/停止。

要点（对应计划"有限步 Agent、步骤状态和调用记录"）：
- 工具循环最多 4 轮（MAX_STEPS），另有总超时保护（DEADLINE_SECONDS）
- 每轮记录"步骤状态"trace：动作、参数、结果概要、耗时、成功/失败
- 四种结束方式：final_answer（成功）/ give_up（无结果或放弃）/
  max_steps（步数用完）/ timeout（超时）—— 计划验收"成功、无结果、超时都能结束"

LLM 通过参数注入（llm_chat）：演示用真模型，测试用 Fake 剧本（计划要求）。
"""

import json
import sys
import time
import urllib.request

from tools import describe_tools, execute_tool

CHAT_MODEL = "qwen3:8b"
OLLAMA = "http://localhost:11434"
MAX_STEPS = 4            # 计划规定：工具循环最多 4 轮
DEADLINE_SECONDS = 180   # 总时间预算：超过就体面结束

SYSTEM_PROMPT = """你是设备运维助手，负责回答设备问题、查询工单、准备工单草稿。

可用工具：
{tools}

决策规则：
1. 需要事实（文档知识、工单数据）时先调用工具，拿到结果再下结论。
2. 不要编造工具没返回的信息。
3. 工具返回 ok=false 或没有结果时，可调整参数重试一次；仍失败就 give_up。
4. 最多 {max_steps} 轮工具调用，请高效决策。

输出协议：只输出一个 JSON 对象，不要输出任何多余文字：
- 调用工具：{{"kind": "tool_call", "name": "工具名", "params": {{...}}}}
- 给出结论：{{"kind": "final_answer", "answer": "..."}}
- 放弃：{{"kind": "give_up", "reason": "..."}}"""


def call_model(messages: list[dict]) -> str:
    # 真模型调用（Ollama /api/chat：JSON 模式、关思考、温度 0）
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": 400},
    }
    req = urllib.request.Request(
        OLLAMA + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["message"]["content"]


def run_agent(question: str, llm_chat=None, max_steps: int = MAX_STEPS,
              deadline_seconds: float = DEADLINE_SECONDS,
              history: list[dict] | None = None,
              user=None) -> dict:
    llm_chat = llm_chat or call_model
    started = time.monotonic()

    # history = 之前几轮对话（计划：Memory 按上下文预算加载，只带最近几条）
    messages = [
        {"role": "system",
         "content": SYSTEM_PROMPT.format(tools=describe_tools(), max_steps=max_steps)},
    ]
    for m in history or []:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": question})

    steps = []  # 调用记录 trace

    for step_no in range(1, max_steps + 1):
        # 超时保护：每轮开始前检查总预算
        if time.monotonic() - started > deadline_seconds:
            return {"status": "timeout", "answer": None,
                    "reason": f"超过时间预算 {deadline_seconds} 秒", "steps": steps}

        t0 = time.monotonic()
        raw = llm_chat(messages)
        elapsed = round((time.monotonic() - t0) * 1000)

        # 解析模型输出；失败时给一次改正机会（概念课第 4 层规范化的兜底）
        try:
            action = json.loads(raw)
            kind = action.get("kind")
        except (json.JSONDecodeError, AttributeError):
            kind = None

        if kind == "tool_call":
            name = action.get("name")
            params = action.get("params", {})
            result = execute_tool(name, params, user)
            steps.append({
                "step": step_no, "kind": "tool_call", "tool": name, "params": params,
                "result": result, "elapsed_ms": elapsed,
                "status": "ok" if result.get("ok") else "error",
            })
            # 把"模型的指令"和"工具的结果"都记进对话，模型下一轮才看得到
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user",
                             "content": f"【工具返回】{json.dumps(result, ensure_ascii=False)}"})
            continue

        if kind in ("final_answer", "give_up"):
            steps.append({"step": step_no, "kind": kind, "action": action,
                          "elapsed_ms": elapsed, "status": "ok"})
            return {"status": kind, "answer": action.get("answer"),
                    "reason": action.get("reason"), "steps": steps}

        # kind 不合法（不是 JSON / 没有 kind / kind 不认识）
        steps.append({"step": step_no, "kind": "invalid_output", "raw": raw[:200],
                      "elapsed_ms": elapsed, "status": "error"})
        if step_no < max_steps:
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user",
                             "content": "你刚才的输出不是合法动作 JSON，请按协议重新输出。"})
            continue
        return {"status": "give_up", "answer": None,
                "reason": "模型输出格式持续不合法", "steps": steps}

    return {"status": "max_steps", "answer": None,
            "reason": f"达到最大步数 {max_steps} 仍未结束", "steps": steps}


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "还有哪些工单没关闭？"
    print(f"问题：{question}\n")

    result = run_agent(question)

    for s in result["steps"]:
        if s["kind"] == "tool_call":
            print(f"[第 {s['step']} 步] 调用 {s['tool']}  参数={json.dumps(s['params'], ensure_ascii=False)}"
                  f"  ({s['elapsed_ms']}ms, {s['status']})")
            print(f"          结果：{json.dumps(s['result'], ensure_ascii=False)[:110]}…")
        else:
            print(f"[第 {s['step']} 步] {s['kind']}  ({s['elapsed_ms']}ms, {s['status']})")

    print(f"\n结束状态：{result['status']}")
    print(f"回答：{result.get('answer') or result.get('reason')}")


if __name__ == "__main__":
    main()
