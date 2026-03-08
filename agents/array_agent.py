"""阵列设计 Agent — 阵列权重计算与 HFSS 端口激励写入。"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agents.tools.array_tools import compute_array_weights, apply_array_excitation
from backend.prompts.system_prompts import ARRAY_SYSTEM_PROMPT

TOOLS = [compute_array_weights, apply_array_excitation]


def _build_executor(rag_context: str | None = None) -> AgentExecutor:
    from backend.llm_factory import build_llm

    llm = build_llm()
    sys_content = ARRAY_SYSTEM_PROMPT
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
    return AgentExecutor(agent=agent, tools=TOOLS, verbose=True, max_iterations=6)


_executor: AgentExecutor | None = None


def get_executor(rag_context: str | None = None) -> AgentExecutor:
    global _executor
    if rag_context or _executor is None:
        return _build_executor(rag_context)
    return _executor


async def run(state: dict) -> dict:
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
        reply = AIMessage(content=f"阵列 Agent 执行出错：{exc}")

    return {**state, "messages": [reply]}
