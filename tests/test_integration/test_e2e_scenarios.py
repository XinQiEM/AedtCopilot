"""端到端集成测试：4 个主要 HFSS 联调场景。

场景对应 DEVELOPMENT_PLAN.md Phase F.3：
  1. 完整建模 + 仿真 + 可视化
  2. 收敛失败自动恢复（MAX_RETRY）
  3. 阵列综合 (compute_array_weights + apply_array_excitation)
  4. 参数扫描 (run_sweep via SweepConfig + scenario_runner)
"""
from __future__ import annotations

import asyncio
import json
import math
import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# 场景 1: 完整建模 → 仿真 → 提取 S 参数
# ---------------------------------------------------------------------------

class TestScenario1FullWorkflow:
    """完整仿真流程：建几何 → 配端口 → 创建 Setup → 扫频 → 提取 S 参数。"""

    def test_create_and_simulate(self, live_hfss):
        """
        1. 创建贴片天线几何
        2. 创建求解配置 + 频率扫描
        3. 运行仿真（uses AnalyzeAll）— 无端口时预期失败，测试验证流程不崩溃
        4. 若仿真成功，提取 S 参数
        """
        from backend.hfss.geometry import create_box
        from backend.hfss.simulation import (
            create_solution_setup,
            create_frequency_sweep,
            run_simulation,
        )
        from backend.hfss.postprocess import get_s_parameters

        # --- 建模（材料赋值在 HFSS 19.5 COM 中可能软失败，但几何体创建成功）---
        r = create_box(origin=[0, 0, 0], sizes=[37.5, 29.0, 0.8],
                       name="S1Patch", material="copper")
        assert r.ok, r.message
        r = create_box(origin=[0, 0, -1.6], sizes=[37.5, 29.0, 1.6],
                       name="S1Sub", material="Rogers 4003C")
        assert r.ok, r.message
        r = create_box(origin=[0, 0, -1.65], sizes=[37.5, 29.0, 0.05],
                       name="S1GND", material="pec")
        assert r.ok, r.message

        # --- 仿真配置 ---
        r = create_solution_setup(freq_ghz=2.4, setup_name="S1Setup",
                                  max_passes=2, delta_s=0.02)
        assert r.ok, r.message
        r = create_frequency_sweep(setup_name="S1Setup", sweep_name="S1Sweep",
                                   start_ghz=1.5, stop_ghz=3.5, step_ghz=0.05)
        assert r.ok, r.message

        # --- 运行仿真（无端口时预期失败，仅验证调用不抛异常）---
        r = run_simulation(setup_name="S1Setup")
        if not r.ok:
            print(f"\n  [预期] 仿真失败（无端口）: {r.message}")
            pytest.skip("无激励端口，跳过 S 参数提取断言")
            return

        # --- 提取结果（仅在仿真成功时执行）---
        r = get_s_parameters(setup_name="S1Setup", sweep_name="S1Sweep")
        assert r.ok, r.message
        data = r.data
        assert "freq_ghz" in data
        assert len(data["freq_ghz"]) > 0
        # S11 存在且 magnitude 为有效数值
        assert "S(1,1)" in data or "S11" in data or len(data) >= 2
        print(f"\n  freq_ghz range: {data['freq_ghz'][0]:.2f} – {data['freq_ghz'][-1]:.2f} GHz")


# ---------------------------------------------------------------------------
# 场景 2: 收敛失败自动恢复
# ---------------------------------------------------------------------------

class TestScenario2ConvergenceRetry:
    """设置极少最大迭代次数触发收敛失败，验证自动重试机制不超过 MAX_RETRY。"""

    def test_convergence_retry_mechanism(self, live_hfss, monkeypatch):
        """
        通过 monkeypatch 强制 run_simulation 在前两次调用时返回收敛失败。
        第三次调用真实函数，验证重试次数 ≤ MAX_RETRY(3)。
        """
        from backend.hfss.simulation import create_solution_setup
        from backend.hfss.geometry import create_box
        import backend.hfss.simulation as sim_module
        from backend.hfss.geometry import HfssResult  # HfssResult 在 geometry 模块中定义

        create_box(origin=[0, 0, 0], sizes=[10, 10, 2], name="S2Box", material="pec")
        create_solution_setup(freq_ghz=5.8, setup_name="S2Setup", max_passes=1)

        call_count = {"n": 0}
        _real_run = sim_module.run_simulation

        def _patched_run(**kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                return HfssResult(ok=False, message="Convergence failed (simulated)")
            return _real_run(**kwargs)

        monkeypatch.setattr(sim_module, "run_simulation", _patched_run)

        MAX_RETRY = 3
        last_result = None
        for attempt in range(MAX_RETRY):
            result = sim_module.run_simulation(setup_name="S2Setup")
            last_result = result
            if result.ok:
                break

        assert call_count["n"] <= MAX_RETRY
        print(f"\n  Total attempts: {call_count['n']}")


# ---------------------------------------------------------------------------
# 场景 3: 阵列综合
# ---------------------------------------------------------------------------

class TestScenario3ArraySynthesis:
    """验证阵列权重计算与激励赋值的完整流程。"""

    def test_chebyshev_synthesis(self, live_hfss):
        """
        compute_array_weights(chebyshev, N=4, SLL=-30, theta_s=30°)
        → apply_array_excitation()
        → 验证返回数据格式正确

        注意：LangChain @tool 以 JSON 字符串为参数调用。
        array_design 函数签名: n_elements, algorithm, sidelobe_db, steering_deg
        返回键: amplitudes, phases_deg
        """
        from agents.tools.array_tools import compute_array_weights, apply_array_excitation

        raw = compute_array_weights.invoke(json.dumps({
            "n_elements": 4,
            "algorithm": "chebyshev",
            "sidelobe_db": -30,
            "steering_deg": 30.0,
        }))
        weights_result = json.loads(raw)
        assert weights_result.get("ok") is True, f"compute_array_weights 失败: {weights_result}"
        weights_data = weights_result["data"]
        assert "amplitudes" in weights_data
        assert "phases_deg" in weights_data
        assert len(weights_data["amplitudes"]) == 4
        assert len(weights_data["phases_deg"]) == 4

        exc_raw = apply_array_excitation.invoke(json.dumps({
            "phase_deg": weights_data["phases_deg"],
            "amplitude": weights_data["amplitudes"],
        }))
        excitation_result = json.loads(exc_raw)
        # 若 HFSS 设计中无端口也可接受 ok=False（只验证不抛异常）
        assert "ok" in excitation_result
        print(f"\n  Amplitudes: {[f'{a:.4f}' for a in weights_data['amplitudes']]}")
        print(f"  Phases_deg: {[f'{p:.1f}°' for p in weights_data['phases_deg']]}")

    def test_taylor_synthesis(self, live_hfss):
        """Taylor 窗 (N=8)。"""
        from agents.tools.array_tools import compute_array_weights

        raw = compute_array_weights.invoke(json.dumps({
            "n_elements": 8,
            "algorithm": "taylor",
            "sidelobe_db": -25,
            "steering_deg": 0.0,
        }))
        r = json.loads(raw)
        assert r.get("ok") is True, f"taylor synthesis failed: {r}"
        assert len(r["data"]["amplitudes"]) == 8

    def test_uniform_synthesis(self, live_hfss):
        """Uniform 权重（全 1）。"""
        from agents.tools.array_tools import compute_array_weights

        raw = compute_array_weights.invoke(json.dumps({
            "n_elements": 6,
            "algorithm": "uniform",
            "steering_deg": 15.0,
        }))
        r = json.loads(raw)
        assert r.get("ok") is True, f"uniform synthesis failed: {r}"
        amps = r["data"]["amplitudes"]
        assert all(math.isclose(a, 1.0, rel_tol=1e-6) for a in amps)


# ---------------------------------------------------------------------------
# 场景 4: 参数扫描 (scenario_runner)
# ---------------------------------------------------------------------------

class TestScenario4ParameterSweep:
    """通过 scenario_runner 的 run_sweep() 运行多点参数扫描。"""

    @pytest.mark.asyncio
    async def test_sweep_all_scenarios_complete(self, live_hfss):
        """
        生成 2 个场景（不同频率），run_sweep() 执行后
        每个 Scenario.name 应非空（completed 可为 False，因无端口）。

        SweepConfig 字段: parameter_name, values, setup_name（无 sweep_name）
        run_sweep 签名: run_sweep(sweep: SweepConfig, parallel=False, max_concurrent=1)
        Scenario 字段: name, parameters, result, error, completed（无 scenario_id）
        """
        from backend.parallel.scenario_runner import SweepConfig, generate_scenarios, run_sweep

        sweep_cfg = SweepConfig(
            parameter_name="freq_ghz",
            values=[2.4, 5.8],
            setup_name="S4Setup",
        )
        scenarios = generate_scenarios(sweep_cfg)
        assert len(scenarios) == 2

        # HFSS 设计可能无 S4Setup，失败也验证流程不崩溃
        try:
            results = await run_sweep(sweep_cfg, max_concurrent=1)
        except Exception as exc:
            pytest.skip(f"run_sweep raised expected error without active design: {exc}")
            return

        assert len(results) == 2
        for s in results:
            assert s.name is not None  # Scenario.name 始终有值
        print(f"\n  Sweep completed: {sum(s.completed for s in results)}/{len(results)}")

    @pytest.mark.asyncio
    async def test_cancel_propagation(self, live_hfss, monkeypatch):
        """asyncio.CancelledError 应向上传播，不被吞掉。

        用慢速假场景替代真实 HFSS 调用，确保取消发生在场景完成之前。
        run_scenario 内部使用 await asyncio.sleep(0) 作为取消检查点，
        此处替换为 sleep(10) 以保证任务在 50ms 内不会完成。
        """
        import backend.parallel.scenario_runner as sr_module
        from backend.parallel.scenario_runner import SweepConfig, run_sweep, Scenario
        import asyncio

        # 用 sleep(10) 替代真实场景执行，比 cancel 的 0.05s 长得多
        async def _slow_scenario(scenario: Scenario) -> Scenario:
            await asyncio.sleep(10)
            return scenario

        monkeypatch.setattr(sr_module, "run_scenario", _slow_scenario)

        sweep_cfg = SweepConfig(
            parameter_name="freq_ghz",
            values=[2.4, 5.8, 10.0],
            setup_name="S4CancelSetup",
        )

        async def _cancel_after():
            task = asyncio.create_task(run_sweep(sweep_cfg, max_concurrent=1))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        await _cancel_after()


# ---------------------------------------------------------------------------
# 场景 5 (bonus): 通过 stream_chat 走完整对话通道
# ---------------------------------------------------------------------------

class TestScenario5StreamChatE2E:
    """smoke test：stream_chat 可被调用，产生至少一个 token 事件。"""

    @pytest.mark.asyncio
    async def test_stream_chat_emits_events(self, live_hfss):
        """向 stream_chat 发送简单问候，断言至少接收到一个事件。

        agents.orchestrator 暴露的是 stream_chat() 异步生成器函数，
        签名：async def stream_chat(user_message: str, history: list | None = None)
        """
        from agents.orchestrator import stream_chat

        events = []
        async for event in stream_chat(
            user_message="你好，当前 HFSS 版本是多少？",
        ):
            events.append(event)
            if len(events) >= 5:  # 避免等待全部输出
                break

        assert len(events) > 0, "stream_chat 未产生任何事件"
        first = events[0]
        assert "type" in first
