"""几何 Agent 单元测试。"""
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage


def _make_state(text: str = "在原点创建 10x5x2 mm 的 PEC 贴片") -> dict:
    return {
        "messages": [HumanMessage(content=text)],
        "intent": "geometry",
        "job_id": None,
        "error": None,
        "rag_context": None,
    }


class TestGeometryAgentRun:
    async def test_run_returns_ai_message(self, fake_executor):
        """run() 应返回含 AIMessage 的新 state。"""
        with patch("agents.geometry_agent.get_executor", return_value=fake_executor):
            from agents.geometry_agent import run
            result = await run(_make_state())

        assert "messages" in result
        last = result["messages"][-1]
        assert isinstance(last, AIMessage)
        assert last.content == "操作执行成功。"

    async def test_run_no_human_message_returns_fallback(self):
        """无 HumanMessage 时应返回含提示的 AIMessage，不崩溃。"""
        from agents.geometry_agent import run
        state = {
            "messages": [],
            "intent": "geometry",
            "job_id": None,
            "error": None,
            "rag_context": None,
        }
        result = await run(state)
        assert isinstance(result["messages"][-1], AIMessage)
        assert "未找到" in result["messages"][-1].content

    async def test_run_executor_error_returns_error_message(self, fake_executor):
        """executor.ainvoke 抛出异常时应捕获并以 AIMessage 形式返回错误描述。"""
        fake_executor.ainvoke.side_effect = RuntimeError("HFSS not connected")
        with patch("agents.geometry_agent.get_executor", return_value=fake_executor):
            from agents.geometry_agent import run
            result = await run(_make_state())

        last = result["messages"][-1]
        assert isinstance(last, AIMessage)
        assert "出错" in last.content or "HFSS" in last.content

    async def test_run_injects_rag_context(self, fake_executor):
        """有 rag_context 时 get_executor 应被传入 rag_context。"""
        state = _make_state()
        state["rag_context"] = "HFSS 参考：CreateBox 参数..."

        with patch("agents.geometry_agent.get_executor", return_value=fake_executor) as mock_get:
            from agents.geometry_agent import run
            await run(state)

        # get_executor 被调用，且传入了 rag_context
        mock_get.assert_called_once_with("HFSS 参考：CreateBox 参数...")

    async def test_run_preserves_existing_state_keys(self, fake_executor):
        """run() 不应丢失 state 中的 intent/job_id/rag_context 等字段。"""
        state = _make_state()
        state["job_id"] = "abc-123"
        state["rag_context"] = "ctx"

        with patch("agents.geometry_agent.get_executor", return_value=fake_executor):
            from agents.geometry_agent import run
            result = await run(state)

        assert result.get("job_id") == "abc-123"
        assert result.get("rag_context") == "ctx"
