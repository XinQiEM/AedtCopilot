"""
顶层 Orchestrator Agent — 意图路由 + 子 Agent 调度。

使用 LangGraph 构建有状态工作流：
  用户消息 → 意图分类 → 路由到子 Agent → 汇总回复
"""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph, add_messages

# 意图类型
Intent = Literal["geometry", "simulation", "postprocess", "array", "general"]


class AppState(TypedDict):
    """全局对话状态。"""
    messages: Annotated[list[BaseMessage], add_messages]
    intent: Intent | None
    job_id: str | None
    error: str | None
    rag_context: str | None  # RAG 检索到的参考文献（注入子 Agent system prompt）


# ---------------------------------------------------------------------------
# 节点函数
# ---------------------------------------------------------------------------

def fetch_rag_context(state: AppState) -> AppState:
    """从向量库检索与最新用户消息相关的 HFSS 文档片段，存入 rag_context。"""
    from backend.rag.retriever import get_retriever

    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    if last_human is None:
        return {**state, "rag_context": None}

    retriever = get_retriever()
    if not retriever.is_ready:
        return {**state, "rag_context": None}

    results = retriever.query(str(last_human.content), top_k=4)
    ctx = retriever.format_context(results) if results else None
    return {**state, "rag_context": ctx}


def classify_intent(state: AppState) -> AppState:
    """根据最新用户消息判断意图。"""
    from backend.llm_factory import build_llm

    llm = build_llm()

    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    if last_human is None:
        return {**state, "intent": "general"}

    prompt = (
        "You are an intent classifier for an HFSS antenna simulation assistant.\n"
        "Classify the user's request into exactly one of these categories:\n"
        "  geometry | simulation | postprocess | array | general\n\n"
        f"User request: {last_human.content}\n\n"
        "Reply with ONLY the category name, nothing else."
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    raw = response.content.strip().lower()
    valid: set[Intent] = {"geometry", "simulation", "postprocess", "array", "general"}
    intent: Intent = raw if raw in valid else "general"  # type: ignore[assignment]
    return {**state, "intent": intent}


def route(state: AppState) -> str:
    """LangGraph 条件路由函数，返回下一个节点名称。"""
    return state.get("intent") or "general"


async def geometry_node(state: AppState) -> AppState:
    from agents.geometry_agent import run as _run
    return await _run(state)


async def simulation_node(state: AppState) -> AppState:
    from agents.simulation_agent import run as _run
    return await _run(state)


async def postprocess_node(state: AppState) -> AppState:
    from agents.postprocess_agent import run as _run
    return await _run(state)


async def array_node(state: AppState) -> AppState:
    from agents.array_agent import run as _run
    return await _run(state)


async def general_node(state: AppState) -> AppState:
    """通用问答节点（无 HFSS 工具，但附带 RAG 上下文）。"""
    from backend.llm_factory import build_llm
    from backend.prompts.system_prompts import ORCHESTRATOR_SYSTEM_PROMPT
    from langchain_core.messages import SystemMessage

    llm = build_llm()
    sys_content = ORCHESTRATOR_SYSTEM_PROMPT
    if state.get("rag_context"):
        sys_content = f"{sys_content}\n\n{state['rag_context']}"
    reply = await llm.ainvoke(
        [SystemMessage(content=sys_content)] + state["messages"]
    )
    return {**state, "messages": [reply]}


# ---------------------------------------------------------------------------
# 构建图
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    g = StateGraph(AppState)

    # RAG 检索节点是第一步
    g.add_node("fetch_rag", fetch_rag_context)
    g.add_node("classify", classify_intent)
    g.add_node("geometry", geometry_node)
    g.add_node("simulation", simulation_node)
    g.add_node("postprocess", postprocess_node)
    g.add_node("array", array_node)
    g.add_node("general", general_node)

    g.set_entry_point("fetch_rag")
    g.add_edge("fetch_rag", "classify")
    g.add_conditional_edges(
        "classify",
        route,
        {
            "geometry": "geometry",
            "simulation": "simulation",
            "postprocess": "postprocess",
            "array": "array",
            "general": "general",
        },
    )
    for node in ("geometry", "simulation", "postprocess", "array", "general"):
        g.add_edge(node, END)

    return g.compile()


# 单例编译图（懒加载）
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def chat(user_message: str, history: list[BaseMessage] | None = None) -> AIMessage:
    """
    外部调用入口：给定用户消息 + 历史，返回完整 AIMessage。
    """
    messages = list(history or []) + [HumanMessage(content=user_message)]
    initial_state: AppState = {
        "messages": messages,
        "intent": None,
        "job_id": None,
        "error": None,
        "rag_context": None,
    }
    result = await get_graph().ainvoke(initial_state)
    ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
    if ai_msgs:
        return ai_msgs[-1]
    return AIMessage(content="[No response generated]")


async def stream_chat(
    user_message: str,
    history: list[BaseMessage] | None = None,
):
    """
    流式对话入口 —— async generator，逐 token yield dict 事件。

    事件格式：
        {"type": "token",       "content": "..."}
        {"type": "intent",      "content": "geometry"}
        {"type": "rag",         "content": "（共 N 条参考）"}
        {"type": "tool_call",   "tool": "create_box", "params": {...}}
        {"type": "tool_result", "ok": true, "message": "已创建 Box1"}
        {"type": "chart",       "chart_type": "s_params"|"far_field", "plotly_json": {...}}
        {"type": "sim_status",  "pass": 3, "delta_s": 0.015, "max_passes": 10, "converged": false}
        {"type": "done",        "content": ""}
        {"type": "error",       "content": "..."}
    """
    import json as _json

    messages = list(history or []) + [HumanMessage(content=user_message)]
    initial_state: AppState = {
        "messages": messages,
        "intent": None,
        "job_id": None,
        "error": None,
        "rag_context": None,
    }

    try:
        _AGENT_NODES = {"geometry", "simulation", "postprocess", "array", "general"}
        _final_content: str | None = None
        _agent_tokens_len: int = 0

        async for event in get_graph().astream_events(initial_state, version="v2"):
            kind = event.get("event", "")
            name = event.get("name", "")
            meta_node = event.get("metadata", {}).get("langgraph_node", "")

            # ── 意图分类完成 ──────────────────────────────────────────────
            if kind == "on_chain_end" and name == "classify":
                data = event.get("data", {})
                output = data.get("output", {})
                intent = output.get("intent") if isinstance(output, dict) else None
                if intent:
                    yield {"type": "intent", "content": intent}

            # ── RAG 检索完成 ───────────────────────────────────────────────
            elif kind == "on_chain_end" and name == "fetch_rag":
                data = event.get("data", {})
                output = data.get("output", {})
                ctx = output.get("rag_context") if isinstance(output, dict) else None
                if ctx:
                    line_count = ctx.count("\n")
                    yield {"type": "rag", "content": f"已检索到 {line_count} 行参考文档"}

            # ── 子 Agent 节点完成 → 兜底：提取最终 AI 回复 ───────────────
            elif kind == "on_chain_end" and name in _AGENT_NODES:
                data = event.get("data", {})
                output = data.get("output", {})
                if isinstance(output, dict):
                    from langchain_core.messages import AIMessage as _AI
                    for msg in reversed(output.get("messages", [])):
                        if isinstance(msg, _AI) and msg.content:
                            _final_content = msg.content
                            break

            # ── LLM 流式 token（仅转发子 Agent 节点的回复，过滤 classify/fetch_rag）──
            elif kind == "on_chat_model_stream" and meta_node in _AGENT_NODES:
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    _agent_tokens_len += len(chunk.content)
                    yield {"type": "token", "content": chunk.content}

            # ── 工具调用开始 ───────────────────────────────────────────────
            elif kind == "on_tool_start":
                raw_input = event.get("data", {}).get("input", {})
                if isinstance(raw_input, str):
                    try:
                        params = _json.loads(raw_input)
                    except Exception:
                        params = {"raw": raw_input}
                else:
                    params = raw_input or {}
                yield {"type": "tool_call", "tool": name, "params": params}

            # ── 工具调用结束 ───────────────────────────────────────────────
            elif kind == "on_tool_end":
                output = event.get("data", {}).get("output")
                raw = ""
                if hasattr(output, "content"):
                    raw = output.content
                elif isinstance(output, str):
                    raw = output

                try:
                    r: dict = _json.loads(raw) if raw else {}
                except Exception:
                    r = {}

                ok = bool(r.get("ok", True))
                message = r.get("message", "")
                if message:  # only emit if there's useful content
                    yield {"type": "tool_result", "ok": ok, "message": message}

                # 后处理图表数据
                chart_data = r.get("data", {}) if isinstance(r, dict) else {}
                if name in ("get_s_parameters", "get_vswr") and isinstance(chart_data, dict) and "freq_ghz" in chart_data:
                    yield {"type": "chart", "chart_type": "s_params", "plotly_json": chart_data}
                elif name == "get_far_field" and isinstance(chart_data, dict) and "theta_deg" in chart_data:
                    yield {"type": "chart", "chart_type": "far_field", "plotly_json": chart_data}
                elif name == "get_convergence_info" and isinstance(chart_data, dict):
                    yield {
                        "type": "sim_status",
                        "pass": chart_data.get("pass", 0),
                        "delta_s": chart_data.get("delta_s", 0.0),
                        "max_passes": chart_data.get("max_passes", 10),
                        "converged": bool(chart_data.get("converged", False)),
                    }

        # done 事件：如果 streaming tokens 不足（未能流式传输），则通过 done 传递最终回复
        done_content = ""
        if _agent_tokens_len < 5 and _final_content:
            done_content = _final_content
        yield {"type": "done", "content": done_content}

    except Exception as exc:
        yield {"type": "error", "content": str(exc)}
