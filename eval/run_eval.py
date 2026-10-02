"""Day 11：冻结评测集 + 跑一次出报告。

用法（在 ops-assistant 目录下）：
    D:/anaconda/envs/spider_env/python.exe -X utf8 eval/run_eval.py --suite rag
    D:/anaconda/envs/spider_env/python.exe -X utf8 eval/run_eval.py --suite agent --mode mock
    D:/anaconda/envs/spider_env/python.exe -X utf8 eval/run_eval.py --suite agent --mode real
    D:/anaconda/envs/spider_env/python.exe -X utf8 eval/run_eval.py --suite all --mode all

三条纪律（对应计划"真实与模拟结果分开，指标有原始记录"）：
1. 题目冻结在 cases_*.json，跑评测只读不改题；要加题就新增 case，不改老题。
2. mock（脚本 Fake，测循环逻辑）和 real（Ollama 真模型，测决策质量）分开跑、分开统计，
   永远不合成一个数字。
3. 每次运行都落盘 reports/<时间>_<套件>-<模式>.json：模型、参数、逐题原始输出全留。

RAG 只有 real 一套 —— 命中/拒答是 embedding 模型的能力，用假向量测没有意义。
"""

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))

from sqlalchemy import select  # noqa: E402

import rag  # noqa: E402
from agent import DEADLINE_SECONDS, MAX_STEPS, run_agent  # noqa: E402
from db import SessionLocal  # noqa: E402
from models import User  # noqa: E402

EVAL_USER = "user1"  # 评测统一用这个账号，报告里记下来，换人等于换数据


def load_cases(filename: str) -> dict:
    return json.loads((HERE / filename).read_text(encoding="utf-8"))


def eval_user() -> User:
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.username == EVAL_USER)).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"数据库里没有 {EVAL_USER}，先在 backend 目录跑 seed.py")
    return user


# ---------------- RAG（只有 real） ----------------

def run_rag(cases: list[dict]) -> list[dict]:
    records = []
    for c in cases:
        expect = c["expect"]
        try:
            hits = rag.search(c["question"])
            titles = [h["title"] for h in hits]
            if expect["type"] == "hit":
                passed = expect["doc"] in titles
                detail = f"期望《{expect['doc']}》｜实得 {titles or '（空）'}"
            else:
                passed = not hits
                detail = f"期望拒答（空）｜实得 {titles}"
            hits_raw = [
                {"score": round(h["score"], 4), "title": h["title"], "preview": h["content"][:60]}
                for h in hits
            ]
        except Exception as exc:  # Ollama 没起 / 数据库连不上
            passed, detail, hits_raw = False, f"运行出错：{exc}", []
        records.append({
            "id": c["id"], "question": c["question"], "why": c["why"],
            "expect": expect, "passed": passed, "detail": detail, "hits": hits_raw,
        })
    return records


def rate(records: list[dict]) -> str:
    if not records:
        return "0/0"
    got = sum(r["passed"] for r in records)
    return f"{got}/{len(records)}（{got / len(records) * 100:.0f}%）"


# ---------------- Agent（mock + real 分开） ----------------

def make_fake(script: list) -> callable:
    # 剧本式 Fake LLM：按 cases_agent.json 里的 script 一步步返回，不调用真模型
    remaining = list(script)

    def fake(messages: list[dict]) -> str:
        if not remaining:
            return '{"kind": "give_up", "reason": "剧本已用尽"}'
        step = remaining.pop(0)
        if "sleep" in step:
            time.sleep(step["sleep"])
        if "__raw__" in step:
            return step["__raw__"]
        return json.dumps(step, ensure_ascii=False)

    return fake


def check_agent(result: dict, expect: dict) -> list[str]:
    problems = []
    want = expect.get("status")
    if want is not None:
        want_list = want if isinstance(want, list) else [want]
        if result["status"] not in want_list:
            problems.append(f"结束状态 {result['status']}，期望 {want_list}")

    if "steps" in expect and len(result["steps"]) != expect["steps"]:
        problems.append(f"步数 {len(result['steps'])}，期望 {expect['steps']}")

    used = [s.get("tool") for s in result["steps"] if s["kind"] == "tool_call"]
    for tool in expect.get("tools_used", []):
        if tool not in used:
            problems.append(f"没调用 {tool}（实际调了 {used or '无'}）")

    codes = [s.get("result", {}).get("error", {}).get("code")
             for s in result["steps"] if s["kind"] == "tool_call"]
    for code in expect.get("error_codes", []):
        if code not in codes:
            problems.append(f"没出现错误码 {code}（实际 {codes}）")

    for idx, want_status in expect.get("step_status", {}).items():
        i = int(idx) - 1
        got = result["steps"][i]["status"] if i < len(result["steps"]) else "（没有这一步）"
        if got != want_status:
            problems.append(f"第 {idx} 步状态 {got}，期望 {want_status}")

    if "reason_contains" in expect and expect["reason_contains"] not in (result.get("reason") or ""):
        problems.append(f"结束原因不含「{expect['reason_contains']}」，实际：{result.get('reason')}")

    return problems


def run_agent_cases(cases: list[dict], mode: str, user: User) -> list[dict]:
    records = []
    for c in cases:
        conf = c.get(mode)
        if conf is None:
            continue  # 这题没有该模式的配置（比如超时题只做 mock）
        started = time.monotonic()
        try:
            if mode == "mock":
                result = run_agent(
                    c["question"],
                    llm_chat=make_fake(conf["script"]),
                    deadline_seconds=conf.get("deadline_seconds", DEADLINE_SECONDS),
                    user=user,
                )
            else:
                result = run_agent(c["question"], user=user, max_steps=MAX_STEPS)
            problems = check_agent(result, conf["expect"])
            error = None
        except Exception as exc:
            result = {"status": "（运行出错）", "steps": [], "answer": None, "reason": None}
            problems, error = [f"运行出错：{exc}"], str(exc)

        records.append({
            "id": c["id"], "question": c["question"], "why": c["why"], "mode": mode,
            "passed": not problems, "problems": problems, "error": error,
            "elapsed_s": round(time.monotonic() - started, 1),
            "status": result["status"], "answer": result.get("answer"),
            "reason": result.get("reason"),
            "manual": conf.get("manual"),  # 有值 = 机械断言之外还需人工判分
            "steps": result["steps"],
        })
    return records


# ---------------- 输出 ----------------

def print_records(records: list[dict]) -> None:
    for r in records:
        mark = "PASS" if r["passed"] else "FAIL"
        detail = r.get("detail") or r.get("answer") or r.get("reason") or ""
        if not r["passed"] and r.get("problems"):
            detail = "；".join(r["problems"])
        print(f"  [{mark}] {r['id']:<32} {str(detail)[:110]}")


def write_report(name: str, payload: dict) -> Path:
    out_dir = HERE / "reports"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}_{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="跑冻结评测集并落盘报告")
    parser.add_argument("--suite", choices=["rag", "agent", "all"], default="all")
    parser.add_argument("--mode", choices=["mock", "real", "all"], default="all")
    args = parser.parse_args()

    if args.suite == "rag" and args.mode == "mock":
        raise SystemExit("RAG 没有 mock 套件：命中/拒答靠真 embedding，假向量测不出东西")

    user = eval_user()
    report = {
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "eval_user": EVAL_USER,
        "suites": {},
    }

    if args.suite in ("rag", "all"):
        cfg = load_cases("cases_rag.json")
        print(f"\n=== RAG 评测（真实：{cfg['params']['embed_model']}，top_k={cfg['params']['top_k']}，"
              f"min_score={cfg['params']['min_score']}）===")
        records = run_rag(cfg["cases"])
        print_records(records)
        hit_cases = [r for r in records if r["expect"]["type"] == "hit"]
        neg_cases = [r for r in records if r["expect"]["type"] == "empty"]
        summary = {"命中率": rate(hit_cases), "拒答正确率": rate(neg_cases), "总通过": rate(records)}
        print(f"  命中率 {summary['命中率']}｜拒答正确率 {summary['拒答正确率']}｜总通过 {summary['总通过']}")
        report["suites"]["rag_real"] = {"params": cfg["params"], "summary": summary, "records": records}

    if args.suite in ("agent", "all"):
        cfg = load_cases("cases_agent.json")
        modes = ["mock", "real"] if args.mode == "all" else [args.mode]
        for mode in modes:
            label = "脚本 Fake（不调用模型）" if mode == "mock" else f"真模型 {cfg['params']['chat_model']}"
            print(f"\n=== Agent 评测 —— {label} ===")
            records = run_agent_cases(cfg["cases"], mode, user)
            if not records:
                print("  （没有该模式的题目）")
                continue
            print_records(records)
            passed = sum(r["passed"] for r in records)
            manual = [r["id"] for r in records if r.get("manual")]
            line = f"  机械断言通过 {passed}/{len(records)}"
            if manual:
                line += f"｜其中 {len(manual)} 题仍需人工判分：{', '.join(manual)}"
            print(line)
            report["suites"][f"agent_{mode}"] = {
                "params": cfg["params"] if mode == "real" else {"llm": "脚本 Fake"},
                "mechanical_passed": f"{passed}/{len(records)}",
                "manual_review": manual,
                "records": records,
            }

    report_name = "rag-real" if args.suite == "rag" else f"{args.suite}-{args.mode}"
    path = write_report(report_name, report)
    print(f"\n原始记录已落盘：{path}")


if __name__ == "__main__":
    main()
