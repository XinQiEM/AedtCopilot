"""
几何 Agent — 负责 HFSS 几何建模相关用户请求的处理。

使用 LangChain Agent + HFSS 几何工具集。
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agents.tools.geometry_tools import (
    create_box,
    create_cylinder,
    create_sphere,
    subtract_objects,
    assign_material,
    list_objects,
    delete_object,
    import_cad_file,
)
from backend.prompts.system_prompts import GEOMETRY_SYSTEM_PROMPT

TOOLS = [
    create_box,
    create_cylinder,
    create_sphere,
    subtract_objects,
    assign_material,
    list_objects,
    delete_object,
    import_cad_file,
]


def _build_executor(rag_context: str | None = None) -> AgentExecutor:
    from backend.llm_factory import build_llm

    llm = build_llm()
    sys_content = GEOMETRY_SYSTEM_PROMPT
    if rag_context:
        sys_content = f"{sys_content}\n\n{rag_context}"
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", sys_content),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, TOOLS, prompt)
    return AgentExecutor(agent=agent, tools=TOOLS, verbose=True, max_iterations=10)


_executor: AgentExecutor | None = None


def get_executor(rag_context: str | None = None) -> AgentExecutor:
    global _executor
    # 有 RAG 上下文时每次新建（确保内容注入）
    if rag_context or _executor is None:
        return _build_executor(rag_context)
    return _executor


async def run(state: dict) -> dict:
    """被 Orchestrator 调用的节点函数（async，支持事件流传播）。"""
    from langchain_core.messages import HumanMessage

    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    if last_human is None:
        return {**state, "messages": [AIMessage(content="未找到用户输入。")]}

    history = state["messages"][:-1]
    rag_context = state.get("rag_context")
    try:
        result = await get_executor(rag_context).ainvoke(
            {"input": last_human.content, "chat_history": history}
        )
        reply = AIMessage(content=result.get("output", ""))
    except Exception as exc:  # noqa: BLE001
        reply = AIMessage(content=f"几何 Agent 执行出错：{exc}")

    return {**state, "messages": [reply]}
