#!/usr/bin/env python
"""HFSS 连通性与基础操作验证脚本。

用法::

    # 基础验证（不运行仿真）
    python scripts/validate_hfss.py

    # 包含仿真步骤
    python scripts/validate_hfss.py --run-sim

    # 静默输出（仅显示 PASS/FAIL 摘要）
    python scripts/validate_hfss.py --quiet

配色方案：
    ✓  绿色 PASS
    ✗  红色 FAIL
    ⚠  黄色 SKIP/WARN
"""
from __future__ import annotations

import argparse
import sys
import textwrap
import time
from typing import Callable, NamedTuple

# ---------------------------------------------------------------------------
# ANSI 颜色
# ---------------------------------------------------------------------------

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"


def _c(color: str, text: str) -> str:
    """在支持颜色的终端中输出带颜色文字。"""
    if sys.stdout.isatty():
        return f"{color}{text}{RESET}"
    return text


# ---------------------------------------------------------------------------
# 步骤结果
# ---------------------------------------------------------------------------

class StepResult(NamedTuple):
    name: str
    passed: bool
    message: str
    duration: float  # 秒


# ---------------------------------------------------------------------------
# 验证步骤
# ---------------------------------------------------------------------------

def _step(name: str, fn: Callable[[], str | None], quiet: bool) -> StepResult:
    """运行单步，捕获异常。fn() 返回 None 代表成功，返回字符串代表跳过原因。"""
    t0 = time.perf_counter()
    try:
        skip_msg = fn()
        ok = True
        msg = skip_msg or "OK"
    except Exception as exc:
        ok = False
        msg = str(exc)
    duration = time.perf_counter() - t0

    icon = _c(GREEN, "✓") if ok else _c(RED, "✗")
    color = GREEN if ok else RED
    if not quiet:
        line = f"  {icon}  {_c(color, name):<40s}  {msg}  ({duration:.2f}s)"
        print(line)
    return StepResult(name=name, passed=ok, message=msg, duration=duration)


# ---------------------------------------------------------------------------
# 主验证逻辑
# ---------------------------------------------------------------------------

def run_validation(run_sim: bool = False, quiet: bool = False) -> int:
    """执行验证流程，返回失败步骤数（0 = 全部通过）。"""
    results: list[StepResult] = []

    if not quiet:
        print(_c(BOLD, "\n===  AedtCopilot  HFSS 验证  ===\n"))

    # --- 步骤 0: 导入 HFSS 客户端 ---
    hfss_client = None

    def step0_import():
        nonlocal hfss_client
        from backend.hfss.com_client import HfssClient, hfss
        # 使用全局单例（geometry/simulation 模块依赖同一实例）
        hfss_client = hfss

    results.append(_step("Step 0  导入 HfssClient", step0_import, quiet))
    if not results[-1].passed:
        _print_summary(results, quiet)
        return 1  # 无法继续

    # --- 步骤 1: COM 连接 ---
    def step1_connect():
        hfss_client.connect()

    results.append(_step("Step 1  COM 连接", step1_connect, quiet))
    if not results[-1].passed:
        _print_summary(results, quiet)
        return 1

    # --- 步骤 2: 版本查询 ---
    def step2_version():
        ver = hfss_client.get_version()
        return f"Version = {ver}"

    results.append(_step("Step 2  版本查询", step2_version, quiet))

    # --- 步骤 3: 列举项目 / 设计 ---
    def step3_projects():
        projects = hfss_client.list_projects()
        designs = hfss_client.list_designs()
        return f"projects={len(projects)}, designs={len(designs)}"

    results.append(_step("Step 3  项目/设计列表", step3_projects, quiet))

    # --- 步骤 3b: 若无活动项目，新建验证用项目+设计 ---
    def step3b_ensure_design():
        """使用 HfssClient.ensure_project() 确保有可用设计（HFSS 19.5 需先保存后才能操作）。"""
        from backend.hfss.com_client import hfss as _hfss
        _hfss.ensure_project(
            save_path=r"D:\Xin\GitCopilot\AedtCopilot\data\ValidationSession.aedt",
            design_name="ValidationDesign",
        )
        # Verify design is accessible
        design = _hfss.get_design()
        if design is None:
            raise RuntimeError("ensure_project() 完成后仍无活动设计")
        return f"活动设计: {design.GetName()}"

    results.append(_step("Step 3b 确认活动设计", step3b_ensure_design, quiet))
    if not results[-1].passed:
        _print_summary(results, quiet)
        return 1

    # --- 步骤 4: 创建测试几何 ---
    def step4_geometry():
        from backend.hfss.geometry import create_box
        r = create_box(origin=[0, 0, 0], sizes=[10, 5, 2],
                       name="ValidationTest_Box", material="pec")
        if not r.ok:
            raise RuntimeError(r.message)

    results.append(_step("Step 4  创建几何体", step4_geometry, quiet))

    # --- 步骤 5: 列举对象，验证刚创建的出现 ---
    def step5_list():
        from backend.hfss.geometry import list_objects
        r = list_objects()
        if not r.ok:
            raise RuntimeError(r.message)
        objs = r.data.get("objects", [])
        if "ValidationTest_Box" not in objs:
            raise RuntimeError(f"ValidationTest_Box not in {objs}")
        return f"{len(objs)} objects"

    results.append(_step("Step 5  列举几何对象", step5_list, quiet))

    # --- 步骤 6: 创建求解配置 ---
    def step6_setup():
        from backend.hfss.simulation import create_solution_setup
        r = create_solution_setup(freq_ghz=2.4, setup_name="ValidationSetup",
                                  max_passes=2, delta_s=0.02)
        if not r.ok:
            raise RuntimeError(r.message)

    results.append(_step("Step 6  创建 SolutionSetup", step6_setup, quiet))

    # --- 步骤 7: 创建频率扫描 ---
    def step7_sweep():
        from backend.hfss.simulation import create_frequency_sweep
        r = create_frequency_sweep(
            setup_name="ValidationSetup",
            sweep_name="ValidationSweep",
            start_ghz=1.0, stop_ghz=3.0, step_ghz=0.1,
        )
        if not r.ok:
            raise RuntimeError(r.message)

    results.append(_step("Step 7  创建频率扫描", step7_sweep, quiet))

    # --- 步骤 8 (可选): 运行仿真 ---
    if run_sim:
        def step8_simulate():
            from backend.hfss.simulation import run_simulation
            r = run_simulation(setup_name="ValidationSetup")
            if not r.ok:
                raise RuntimeError(r.message)

        results.append(_step("Step 8  运行仿真 (AnalyzeAll)", step8_simulate, quiet))

        # --- 步骤 9: 提取 S 参数 ---
        def step9_sparams():
            from backend.hfss.postprocess import get_s_parameters
            r = get_s_parameters(setup_name="ValidationSetup",
                                 sweep_name="ValidationSweep")
            if not r.ok:
                raise RuntimeError(r.message)
            n = len(r.data.get("freq_ghz", []))
            return f"{n} frequency points"

        results.append(_step("Step 9  提取 S 参数", step9_sparams, quiet))

    # --- 步骤 10: 清理测试对象 ---
    def step_cleanup():
        from backend.hfss.geometry import delete_object
        for name in ["ValidationTest_Box"]:
            try:
                delete_object(name)
            except Exception:
                pass  # 忽略清理错误
        # 关闭验证用项目（若是本脚本创建的）
        try:
            proj = hfss_client.get_project()
            if proj is not None:
                name = proj.GetName() if hasattr(proj, 'GetName') else ''
                if 'Validation' in str(name) or 'Session' in str(name):
                    proj.Close()
        except Exception:
            pass

    results.append(_step("Step 10 清理测试对象", step_cleanup, quiet))

    return _print_summary(results, quiet)


def _print_summary(results: list[StepResult], quiet: bool) -> int:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    failed = total - passed

    if not quiet:
        print()
    bar = _c(GREEN, f"{passed}/{total} PASSED") if failed == 0 else _c(RED, f"{passed}/{total} PASSED, {failed} FAILED")
    print(f"  {_c(BOLD, 'Summary')}  {bar}")

    if failed:
        print()
        for r in results:
            if not r.passed:
                print(f"    {_c(RED, '✗')}  {r.name}: {r.message}")
    print()
    return failed


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="验证本机 HFSS COM 接口是否可用",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              python scripts/validate_hfss.py
              python scripts/validate_hfss.py --run-sim
              python scripts/validate_hfss.py --quiet
        """),
    )
    parser.add_argument("--run-sim", action="store_true",
                        help="包含完整仿真步骤（耗时较长）")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="静默模式，仅输出摘要")
    args = parser.parse_args()

    sys.exit(run_validation(run_sim=args.run_sim, quiet=args.quiet))


if __name__ == "__main__":
    main()
