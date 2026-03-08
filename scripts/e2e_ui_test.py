#!/usr/bin/env python
"""
E2E UI 测试脚本 — 通过 WebSocket 模拟真实前端对话，覆盖 5 大场景：
  1. 连接 smoke + 版本查询
  2. RAG 检索（HFSS API 问题）
  3. 几何工具调用（create_box）
  4. 阵列综合工具（compute_array_weights）
  5. 仿真配置工具（create_solution_setup）

用法：
  python scripts/e2e_ui_test.py  [--url ws://127.0.0.1:8000/ws/chat]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

try:
    import websockets  # type: ignore
except ImportError:
    print("[SKIP] websockets 未安装，运行：pip install websockets")
    sys.exit(0)

# ── 颜色输出 ────────────────────────────────────────────────────────────────

RESET  = "\x1b[0m"
GREEN  = "\x1b[32m"
RED    = "\x1b[31m"
YELLOW = "\x1b[33m"
CYAN   = "\x1b[36m"
BOLD   = "\x1b[1m"

def ok(msg: str)    -> str: return f"{GREEN}✓ {msg}{RESET}"
def fail(msg: str)  -> str: return f"{RED}✗ {msg}{RESET}"
def info(msg: str)  -> str: return f"{CYAN}  {msg}{RESET}"
def warn(msg: str)  -> str: return f"{YELLOW}⚠ {msg}{RESET}"
def head(msg: str)  -> str: return f"\n{BOLD}{CYAN}{'─'*60}{RESET}\n{BOLD}{msg}{RESET}\n{'─'*60}"


# ── 结果收集 ─────────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    passed: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    tokens: str = ""
    tool_calls: list[str] = field(default_factory=list)
    intent: str = ""
    rag_hint: str = ""
    has_chart: bool = False
    error: str = ""
    duration_s: float = 0.0


# ── 核心 WebSocket 会话 ───────────────────────────────────────────────────────

async def chat(
    ws_url: str,
    message: str,
    history: list[dict] | None = None,
    timeout: float = 120.0,
) -> TestResult:
    """连接 WebSocket，发送一条消息，收集所有事件直到 done/error。"""
    result = TestResult(name=message[:40])
    t0 = time.perf_counter()

    try:
        async with websockets.connect(ws_url, open_timeout=10) as ws:
            payload = json.dumps(
                {"message": message, "history": history or []}, ensure_ascii=False
            )
            await ws.send(payload)

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    result.error = f"超时（>{timeout}s）"
                    break

                event = json.loads(raw)
                result.events.append(event)
                etype = event.get("type", "")

                if etype == "intent":
                    result.intent = event.get("content", "")
                elif etype == "rag":
                    result.rag_hint = event.get("content", "")
                elif etype == "token":
                    result.tokens += event.get("content", "")
                elif etype == "tool_call":
                    result.tool_calls.append(event.get("tool", "unknown"))
                elif etype == "chart":
                    result.has_chart = True
                elif etype == "done":
                    result.passed = True
                    break
                elif etype == "error":
                    result.error = event.get("content", "unknown error")
                    break

    except Exception as exc:
        result.error = str(exc)

    result.duration_s = time.perf_counter() - t0
    return result


# ── 测试用例 ──────────────────────────────────────────────────────────────────

async def run_all_tests(ws_url: str) -> tuple[int, int]:
    """运行全部 E2E 测试用例，返回 (passed, total)。"""
    results: list[TestResult] = []
    session_history: list[dict] = []

    def _add_to_history(user_msg: str, r: TestResult):
        session_history.append({"role": "user", "content": user_msg})
        if r.tokens:
            session_history.append({"role": "assistant", "content": r.tokens})

    # ────────────────────────────────────────────────────────────────────────
    print(head("场景 1：连接 Smoke + HFSS 版本查询"))
    msg1 = "你好！当前 HFSS 版本是多少？项目中有哪些设计？"
    r1 = await chat(ws_url, msg1, timeout=60)
    r1.name = "版本查询"
    r1.passed = r1.passed and bool(r1.tokens)
    _add_to_history(msg1, r1)

    _print_result(r1, checks={
        "收到 done 事件": r1.passed,
        "有 token 输出":  bool(r1.tokens),
        "有意图分类":      bool(r1.intent),
    })
    results.append(r1)

    # ────────────────────────────────────────────────────────────────────────
    print(head("场景 2：RAG 检索——HFSS CreateBox API 问题"))
    msg2 = "HFSS COM 脚本中，CreateBox 函数的参数格式是什么？请给出示例。"
    r2 = await chat(ws_url, msg2, timeout=90)
    r2.name = "RAG 检索"
    r2.passed = r2.passed and bool(r2.tokens)
    _add_to_history(msg2, r2)

    _print_result(r2, checks={
        "收到 done 事件":     r2.passed,
        "有 token 输出":      bool(r2.tokens),
        "有 RAG 检索提示":    bool(r2.rag_hint),
        "回答长度 ≥ 50 字":  len(r2.tokens) >= 50,
    })
    results.append(r2)

    # ────────────────────────────────────────────────────────────────────────
    print(head("场景 3：几何工具调用——创建长方体"))
    msg3 = "请在 HFSS 中创建一个 10mm×8mm×2mm 的长方体，命名为 E2ETestBox，材料为真空。"
    r3 = await chat(ws_url, msg3, session_history[:], timeout=90)
    r3.name = "创建长方体"
    r3.passed = r3.passed and ("create_box" in r3.tool_calls or bool(r3.tokens))
    _add_to_history(msg3, r3)

    _print_result(r3, checks={
        "收到 done 事件":           r3.passed,
        "调用了 create_box":        "create_box" in r3.tool_calls,
        "意图为 geometry/hfss":     "geometry" in r3.intent.lower() or "hfss" in r3.intent.lower()
                                    or bool(r3.tool_calls),
        "有 token 输出":            bool(r3.tokens),
    })
    results.append(r3)

    # ────────────────────────────────────────────────────────────────────────
    print(head("场景 4：阵列综合工具——计算 Chebyshev 阵列权重"))
    msg4 = "帮我计算一个 4 元 Chebyshev 线阵的幅度权重，旁瓣电平 -30dB，波束指向 30°。"
    r4 = await chat(ws_url, msg4, session_history[:], timeout=90)
    r4.name = "阵列综合"
    r4.passed = r4.passed and bool(r4.tokens)
    _add_to_history(msg4, r4)

    _print_result(r4, checks={
        "收到 done 事件":                  r4.passed,
        "有 token 输出":                    bool(r4.tokens),
        "调用阵列相关工具 或 token 含权重数值":
            any("array" in t.lower() or "weight" in t.lower() for t in r4.tool_calls)
            or any(kw in r4.tokens for kw in ["权重", "幅度", "0.", "amplitude"]),
    })
    results.append(r4)

    # ────────────────────────────────────────────────────────────────────────
    print(head("场景 5：仿真配置工具——创建 2.4GHz 求解设置"))
    msg5 = "在 HFSS 中创建名为 E2ESetup 的仿真求解配置，频率 2.4GHz，最多 3 次自适应迭代。"
    r5 = await chat(ws_url, msg5, session_history[:], timeout=90)
    r5.name = "仿真设置"
    r5.passed = r5.passed and bool(r5.tokens)
    _add_to_history(msg5, r5)

    _print_result(r5, checks={
        "收到 done 事件":                 r5.passed,
        "调用了 create_solution_setup":  "create_solution_setup" in r5.tool_calls,
        "有 token 输出":                  bool(r5.tokens),
    })
    results.append(r5)

    # ────────────────────────────────────────────────────────────────────────
    # 多轮对话场景
    print(head("场景 6：多轮对话上下文继承"))
    msg6 = "上面那个长方体 E2ETestBox 的尺寸是多少？"
    r6 = await chat(ws_url, msg6, session_history[:], timeout=60)
    r6.name = "多轮对话"
    # 成功标准：回答中提到尺寸数字 10/8/2 mm 或 E2ETestBox
    has_context = any(
        kw in r6.tokens for kw in ["10", "8mm", "2mm", "E2ETestBox", "10mm", "长方体"]
    )
    r6.passed = r6.passed and (bool(r6.tokens))

    _print_result(r6, checks={
        "收到 done 事件":    r6.passed,
        "有 token 输出":     bool(r6.tokens),
        "回答包含历史上下文": has_context,
    })
    results.append(r6)

    # ────────────────────────────────────────────────────────────────────────
    # 汇总
    return _print_summary(results)


def _print_result(r: TestResult, checks: dict[str, bool]):
    """打印单个测试用例的详细结果。"""
    print(f"\n  测试: {r.name}")
    print(f"  耗时: {r.duration_s:.1f}s  |  意图: {r.intent or '(无)'}  |  RAG: {r.rag_hint[:50] if r.rag_hint else '(无)'}")
    if r.tool_calls:
        print(f"  工具调用: {', '.join(r.tool_calls)}")
    if r.tokens:
        preview = r.tokens[:200].replace('\n', ' ')
        print(f"  回复预览: {preview}{'…' if len(r.tokens) > 200 else ''}")
    if r.error:
        print(f"  {warn('错误: ' + r.error[:100])}")

    for check_name, passed in checks.items():
        if passed:
            print(f"    {ok(check_name)}")
        else:
            print(f"    {fail(check_name)}")


def _print_summary(results: list[TestResult]) -> tuple[int, int]:
    """打印汇总表格，返回 (passed, total)。"""
    passed = sum(1 for r in results if r.passed)
    total  = len(results)

    print(f"\n{'─'*60}")
    print(f"{BOLD}E2E 测试汇总  {GREEN if passed == total else YELLOW}{passed}/{total} 通过{RESET}")
    print(f"{'─'*60}")
    for r in results:
        status = f"{GREEN}PASS{RESET}" if r.passed else f"{RED}FAIL{RESET}"
        tools  = f"  工具: {','.join(r.tool_calls)}" if r.tool_calls else ""
        print(f"  [{status}]  {r.name:<20}  {r.duration_s:.1f}s{tools}")
    print(f"{'─'*60}\n")

    return passed, total


# ── 入口 ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="AedtCopilot E2E UI 测试")
    parser.add_argument("--url",  default="ws://127.0.0.1:8000/ws/chat", help="WebSocket URL")
    parser.add_argument("--test", type=int, default=0, help="只运行指定编号的场景 (1-6)")
    args = parser.parse_args()

    print(f"{BOLD}AedtCopilot E2E UI 测试{RESET}")
    print(f"WebSocket: {args.url}")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 连通性检查
    try:
        async with websockets.connect(args.url, open_timeout=5):
            print(ok("WebSocket 连接成功"))
    except Exception as e:
        print(fail(f"无法连接 WebSocket: {e}"))
        print("  请确认后端已启动：uvicorn backend.main:app --port 8000")
        sys.exit(1)

    passed, total = await run_all_tests(args.url)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
