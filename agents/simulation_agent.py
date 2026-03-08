"""
仿真 Agent — 负责 HFSS 仿真配置、运行与监控的用户请求处理。

使用 LangChain Agent + 仿真工具集（LLM-driven），支持：
  - 创建/更新 Solution Setup（create_solution_setup）
  - 创建频率扫描（create_frequency_sweep）
  - 指定边界条件和端口（assign_radiation_boundary / assign_lumped_port）
  - 运行仿真（run_simulation）
  - 检查收敛（get_convergence_info）

重试逻辑由 AgentExecutor 通过工具结果判断，最多 MAX_RETRY 次。
"""
from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agents.tools.simulation_tools import (
    assign_radiation_boundary,
    assign_lumped_port,
    assign_plane_wave,
    create_solution_setup,
    create_frequency_sweep,
    run_simulation,
    get_convergence_info,
)
from agents.tools.geometry_tools import list_objects
from backend.prompts.system_prompts import SIMULATION_SYSTEM_PROMPT

MAX_RETRY = 3  # 最大工具调用轮次

TOOLS = [
    create_solution_setup,
    create_frequency_sweep,
    assign_radiation_boundary,
    assign_lumped_port,
    assign_plane_wave,
    run_simulation,
    get_convergence_info,
    list_objects,
]


def _build_executor(rag_context: str | None = None) -> AgentExecutor:
    from backend.llm_factory import build_llm

    llm = build_llm()
    sys_content = SIMULATION_SYSTEM_PROMPT
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
    return AgentExecutor(agent=agent, tools=TOOLS, verbose=True,
                         max_iterations=MAX_RETRY + 2)


_executor: AgentExecutor | None = None


def get_executor(rag_context: str | None = None) -> AgentExecutor:
    global _executor
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
        reply = AIMessage(content=f"仿真 Agent 执行出错：{exc}")

    return {**state, "messages": [reply]}
