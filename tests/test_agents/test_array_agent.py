"""阵列 Agent 与阵列算法单元测试。"""
import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage


# ---------------------------------------------------------------------------
# Pure-Python algorithm tests (no COM, no LLM)
# ---------------------------------------------------------------------------

class TestComputeArrayWeights:
    """直接测试 backend.hfss.array_design.compute_array_weights。"""

    @pytest.mark.parametrize("algorithm", [
        "uniform", "chebyshev", "taylor", "cosine", "hamming", "binomial",
    ])
    def test_all_algorithms_return_correct_shape(self, algorithm):
        """每种算法应输出长度与 n_elements 一致的幅度和相位列表。"""
        from backend.hfss.array_design import compute_array_weights
        n = 8
        result = compute_array_weights(n_elements=n, algorithm=algorithm, sidelobe_db=-25)
        assert len(result["amplitudes"]) == n
        assert len(result["phases_deg"]) == n

    def test_uniform_amplitudes_all_one(self):
        """均匀加权时所有幅度应归一化为 1.0。"""
        from backend.hfss.array_design import compute_array_weights
        result = compute_array_weights(n_elements=4, algorithm="uniform")
        assert all(abs(a - 1.0) < 1e-9 for a in result["amplitudes"])

    def test_af_data_coverage(self):
        """阵列因子 theta_deg 应覆盖 -90° ~ +90°（1801 点）。"""
        from backend.hfss.array_design import compute_array_weights
        result = compute_array_weights(n_elements=4)
        af = result["af_data"]
        assert len(af["theta_deg"]) == 1801
        assert len(af["AF_dB"]) == 1801
        assert af["theta_deg"][0] == pytest.approx(-90.0)
        assert af["theta_deg"][-1] == pytest.approx(90.0)

    def test_steering_shifts_phase(self):
        """指向角非零时相位应不全为零。"""
        from backend.hfss.array_design import compute_array_weights
        result = compute_array_weights(n_elements=4, steering_deg=30.0)
        phases = result["phases_deg"]
        assert not all(abs(p) < 1e-9 for p in phases)

    def test_invalid_algorithm_raises(self):
        """传入未知算法名时应抛出 ValueError。"""
        from backend.hfss.array_design import compute_array_weights
        with pytest.raises(ValueError, match="未知算法"):
            compute_array_weights(n_elements=4, algorithm="invalid_algo")


class TestApplyArrayExcitation:
    """测试 apply_array_excitation（无 COM 时静默跳过端口写入）。"""

    def test_returns_port_mapping(self):
        """应返回端口名 → 幅度/相位映射字典。"""
        from backend.hfss.array_design import apply_array_excitation
        result = apply_array_excitation(
            phase_deg=[0.0, 45.0, 90.0],
            amplitude=[1.0, 0.8, 0.6],
        )
        assert "P1" in result
        assert result["P1"]["amplitude"] == pytest.approx(1.0)
        assert result["P3"]["phase_deg"] == pytest.approx(90.0)

    def test_default_amplitude_when_omitted(self):
        """省略 amplitude 时默认幅度应均为 1.0。"""
        from backend.hfss.array_design import apply_array_excitation
        result = apply_array_excitation(phase_deg=[0.0, 0.0])
        assert result["P1"]["amplitude"] == pytest.approx(1.0)
        assert result["P2"]["amplitude"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Tool wrapper tests
# ---------------------------------------------------------------------------

class TestArrayToolWrappers:
    def test_compute_array_weights_tool_returns_ok_true(self):
        """compute_array_weights 工具调用成功时应返回 ok=True。"""
        from agents.tools.array_tools import compute_array_weights as tool_fn
        payload = json.dumps({
            "n_elements": 4,
            "algorithm": "uniform",
        })
        raw = tool_fn.invoke(payload)
        result = json.loads(raw)
        assert result["ok"] is True
        assert "data" in result
        assert "amplitudes" in result["data"]

    def test_compute_array_weights_tool_unknown_algo(self):
        """传入非法算法时工具应返回 ok=False 而不是抛出异常。"""
        from agents.tools.array_tools import compute_array_weights as tool_fn
        payload = json.dumps({"n_elements": 4, "algorithm": "UNKNOWN"})
        raw = tool_fn.invoke(payload)
        result = json.loads(raw)
        assert result["ok"] is False

    def test_apply_array_excitation_tool_returns_ok_true(self):
        """apply_array_excitation 工具（无 COM）应返回 ok=True。"""
        from agents.tools.array_tools import apply_array_excitation as tool_fn
        payload = json.dumps({
            "phase_deg": [0.0, 45.0],
            "amplitude": [1.0, 0.8],
        })
        raw = tool_fn.invoke(payload)
        result = json.loads(raw)
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Agent run() tests
# ---------------------------------------------------------------------------

def _make_state(text: str = "用 Chebyshev 加权设计 8 元阵，旁瓣电平 -30 dB") -> dict:
    return {
        "messages": [HumanMessage(content=text)],
        "intent": "array",
        "job_id": None,
        "error": None,
        "rag_context": None,
    }


class TestArrayAgentRun:
    async def test_run_returns_ai_message(self, fake_executor):
        """run() 应返回含 AIMessage 的新 state。"""
        with patch("agents.array_agent.get_executor", return_value=fake_executor):
            from agents.array_agent import run
            result = await run(_make_state())

        last = result["messages"][-1]
        assert isinstance(last, AIMessage)
        assert last.content == "操作执行成功。"

    async def test_run_no_human_message_returns_fallback(self):
        """无 HumanMessage 时应返回含提示的 AIMessage。"""
        from agents.array_agent import run
        state = {
            "messages": [],
            "intent": "array",
            "job_id": None,
            "error": None,
            "rag_context": None,
        }
        result = await run(state)
        assert isinstance(result["messages"][-1], AIMessage)
        assert "未找到" in result["messages"][-1].content

    async def test_run_executor_error_returns_error_message(self, fake_executor):
        """executor.ainvoke 抛出异常时应捕获并以 AIMessage 返回错误描述。"""
        fake_executor.ainvoke.side_effect = RuntimeError("API timeout")
        with patch("agents.array_agent.get_executor", return_value=fake_executor):
            from agents.array_agent import run
            result = await run(_make_state())

        last = result["messages"][-1]
        assert isinstance(last, AIMessage)
        assert "出错" in last.content or "API" in last.content

    async def test_run_passes_rag_context_to_executor(self, fake_executor):
        """有 rag_context 时 get_executor 应传入对应字符串。"""
        state = _make_state()
        state["rag_context"] = "阵列加权参考..."

        with patch("agents.array_agent.get_executor", return_value=fake_executor) as mock_get:
            from agents.array_agent import run
            await run(state)

        mock_get.assert_called_once_with("阵列加权参考...")
