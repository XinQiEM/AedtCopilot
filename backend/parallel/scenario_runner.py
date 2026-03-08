"""
并行参数扫描运行器 — 在多个参数场景下顺序（或并行）运行 HFSS 仿真。

AEDT 19.5 默认单用户 License，因此有 License 竞争检测，会自动串行降级。
阶段 D 实现，此处为骨架。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class LicenseError(RuntimeError):
    """HFSS License 资源不足时抛出。"""


@dataclass
class Scenario:
    """一个参数扫描场景的定义。"""
    name: str
    parameters: dict[str, Any]  # 例如 {"freq_ghz": 2.4, "patch_length": 38.5}
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    completed: bool = False


@dataclass
class SweepConfig:
    """参数扫描配置。"""
    parameter_name: str
    values: list[Any]
    setup_name: str = "Setup1"


def generate_scenarios(sweep: SweepConfig) -> list[Scenario]:
    """根据扫描配置生成场景列表。"""
    return [
        Scenario(
            name=f"{sweep.parameter_name}={v}",
            parameters={sweep.parameter_name: v, "setup_name": sweep.setup_name},
        )
        for v in sweep.values
    ]


async def run_scenario(scenario: Scenario) -> Scenario:
    """
    执行单个场景：修改 HFSS 设计变量 → 运行仿真 → 提取 S 参数和远场。

    参数更新策略：
      scenario.parameters 中的 "setup_name" 键用于选择求解配置；
      其余键均视为 HFSS 设计变量，通过 SetVariableValue 写入。

    注意：HFSS COM 对象属于 STA（单线程套间），不能跨线程访问。
    因此所有 COM 调用直接在事件循环线程中同步执行，不使用 run_in_executor。
    """
    logger.info("运行场景: %s", scenario.name)
    try:
        from backend.hfss.com_client import hfss
        from backend.hfss.simulation import run_simulation
        from backend.hfss.postprocess import get_s_parameters, get_far_field

        setup_name = scenario.parameters.get("setup_name", "Setup1")
        sweep_name = scenario.parameters.get("sweep_name", "Sweep1")

        # ① 将场景参数写入 HFSS 设计变量（直接同步调用，COM 为 STA 不可跨线程）
        await asyncio.sleep(0)  # 让事件循环处理其他待办事项
        design = hfss.get_design()

        skip_keys = {"setup_name", "sweep_name"}
        for key, val in scenario.parameters.items():
            if key in skip_keys:
                continue
            design.SetVariableValue(key, str(val))
            logger.debug("  SetVariableValue(%s, %s)", key, val)

        await asyncio.sleep(0)

        # ② 运行仿真
        result = run_simulation(setup_name=setup_name)
        if not result.ok:
            raise RuntimeError(f"仿真失败: {result.message}")

        await asyncio.sleep(0)

        # ③ 提取结果
        sp = get_s_parameters(setup_name=setup_name, sweep_name=sweep_name)
        ff = get_far_field(setup_name=setup_name)

        scenario.result = {
            "s_parameters": sp.data if sp.ok else {"error": sp.message},
            "far_field":    ff.data if ff.ok else {"error": ff.message},
        }
        scenario.completed = True
        logger.info("场景 %s 完成", scenario.name)

    except LicenseError:
        raise  # 让上层 run_sweep 捕获并降级串行
    except Exception as exc:
        logger.error("场景 %s 失败: %s", scenario.name, exc)
        scenario.error = str(exc)
        scenario.completed = False

    return scenario


async def run_sweep(
    sweep: SweepConfig,
    parallel: bool = False,
    max_concurrent: int = 1,
) -> list[Scenario]:
    """
    执行参数扫描。

    Args:
        sweep:          扫描配置
        parallel:       是否尝试并行（需要多 License）
        max_concurrent: 最大并发数（License 受限时自动降为 1）

    Returns:
        所有场景的结果列表
    """
    scenarios = generate_scenarios(sweep)
    logger.info(
        "开始参数扫描：%s，共 %d 个场景，%s",
        sweep.parameter_name,
        len(scenarios),
        "并行模式" if parallel else "串行模式",
    )

    if parallel and max_concurrent > 1:
        try:
            semaphore = asyncio.Semaphore(max_concurrent)

            async def _bounded(s: Scenario) -> Scenario:
                async with semaphore:
                    return await run_scenario(s)

            results = await asyncio.gather(*[_bounded(s) for s in scenarios])
            return list(results)
        except LicenseError:
            logger.warning("License 不足，回退到串行模式")

    # 串行执行
    for scenario in scenarios:
        await run_scenario(scenario)

    return scenarios


def format_sweep_summary(scenarios: list[Scenario]) -> str:
    """生成参数扫描结果摘要。"""
    lines = [f"参数扫描完成：{len(scenarios)} 个场景"]
    ok = [s for s in scenarios if s.completed]
    fail = [s for s in scenarios if not s.completed]
    lines.append(f"  成功: {len(ok)} | 失败: {len(fail)}")
    for s in fail:
        lines.append(f"  ✗ {s.name}: {s.error}")
    return "\n".join(lines)
