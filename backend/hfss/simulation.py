from backend.hfss.com_client import hfss
from backend.hfss.geometry import HfssResult


# ---------------------------------------------------------------------------
# 边界条件与端口
# ---------------------------------------------------------------------------

def assign_radiation_boundary(obj_names: list[str] | None = None, boundary_name: str = "Rad1") -> HfssResult:
    """为指定面/对象指定辐射边界条件。obj_names 为空时默认使用 ["Region"]。"""
    if not obj_names:
        obj_names = ["Region"]
    module = hfss.get_design().GetModule("BoundarySetup")
    try:
        # 若同名边界已存在，先删除
        try:
            existing = module.GetBoundaries()
            if boundary_name in (existing or []):
                module.DeleteBoundaries([boundary_name])
        except Exception:
            pass
        module.AssignRadiation(
            ["NAME:" + boundary_name,
             "Objects:=",     obj_names,
             "IsIncidentField:=", False,
             "IsEnforcedField:=", False,
             "IsFssReference:=",  False,
             "IsForPML:=",        False,
             "UseAdaptiveIE:=",   False,
             "IncludeInPostproc:=", True],
        )
        return HfssResult(ok=True, message=f"已指定辐射边界 {boundary_name}")
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def assign_lumped_port(
    obj_name: str,
    port_name: str = "P1",
    impedance: float = 50.0,
) -> HfssResult:
    """在指定面上创建集总端口（Lumped Port）。"""
    module = hfss.get_design().GetModule("BoundarySetup")
    try:
        # 若同名端口已存在，先删除
        try:
            existing = module.GetExcitations()
            if port_name in (existing or []):
                module.DeleteBoundaries([port_name])
        except Exception:
            pass
        module.AssignLumpedPort(
            ["NAME:" + port_name,
             "Objects:=",      [obj_name],
             "RenormalizeAllTerminals:=", True,
             "DoDeembed:=",    False,
             ["NAME:Modes",
              ["NAME:Mode1",
               "ModeNum:=",  1,
               "UseIntLine:=", False]],
             "ShowReporterFilter:=", False,
             "ReporterFilter:=",    [True],
             "FullResistance:=",    f"{impedance}ohm",
             "FullReactance:=",     "0ohm"],
        )
        return HfssResult(ok=True, message=f"已创建集总端口 {port_name}（{impedance}Ω）")
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def assign_plane_wave(
    wave_name: str = "PlaneWave1",
    freq_mhz: float = 300.0,
    theta_deg: float = 0.0,
    phi_deg: float = 0.0,
    polarization: str = "linear_v",
) -> HfssResult:
    """设置平面波激励（入射波 / Incident Wave）。

    参数：
    - wave_name:    激励名称（默认 "PlaneWave1"）
    - freq_mhz:     频率（MHz，仅用于记录，实际频率由 Setup 决定）
    - theta_deg:    入射角 θ（相对 Z 轴，0°=沿+Z，90°=水平入射）
    - phi_deg:      方位角 φ（从 X 轴起，0°~360°）
    - polarization: "linear_v"（θ/垂直极化，默认）或 "linear_h"（φ/水平极化）

    HFSS 19.5 COM API 使用角度参数（Pitch/Yaw/Roll）而非笛卡尔向量：
      PropagationYaw=φ, PropagationPitch=θ（从 Z 轴量起）
      PolarizationRoll=0° → θ 极化；=90° → φ 极化
    """
    try:
        design = hfss.get_design()
        module = design.GetModule("BoundarySetup")

        # 若同名激励已存在，先删除（避免 COM "发生意外" 错误）
        try:
            existing = module.GetExcitations()
            if wave_name in (existing or []):
                module.DeleteBoundaries([wave_name])
        except Exception:
            pass

        pol_roll = "90deg" if polarization == "linear_h" else "0deg"
        pol_label = "φ 极化（水平）" if polarization == "linear_h" else "θ 极化（垂直）"

        module.AssignPlaneWave([
            "NAME:" + wave_name,
            "IsLinearPolarization:=", True,
            "EFieldMag:=",           "1V_per_m",
            "PhaseDelay:=",          "0deg",
            "PropagationYaw:=",      f"{phi_deg}deg",
            "PropagationPitch:=",    f"{theta_deg}deg",
            "PolarizationRoll:=",    pol_roll,
        ])
        freq_str = f"{freq_mhz}MHz"
        return HfssResult(
            ok=True,
            message=(
                f"已设置平面波激励 {wave_name}（{freq_str}，"
                f"θ={theta_deg}°，φ={phi_deg}°，{pol_label}）"
            ),
        )
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


# ---------------------------------------------------------------------------
# 求解设置
# ---------------------------------------------------------------------------

def create_solution_setup(
    setup_name: str = "Setup1",
    freq_ghz: float = 2.4,
    max_passes: int = 20,
    delta_s: float = 0.02,
    min_passes: int = 2,
) -> HfssResult:
    """创建 HFSS Driven Modal 求解设置。若同名 Setup 已存在，先删除再重建。

    注意：HFSS 19.5 COM 中 IsEnabled:= 须使用整数 1/0，不能用 Python bool。
    """
    module = hfss.get_design().GetModule("AnalysisSetup")
    try:
        # 若同名 Setup 已存在，先删除（避免 COM ERROR_PATH_NOT_FOUND）
        try:
            existing = module.GetSetups()  # 返回 tuple 或 list
            if setup_name in (existing or []):
                module.DeleteSetups([setup_name])
        except Exception:
            pass  # GetSetups 不存在时忽略

        module.InsertSetup("HfssDriven", [
            "NAME:" + setup_name,
            "Frequency:=",                f"{freq_ghz}GHz",
            "MaximumPasses:=",            max_passes,
            "MinimumPasses:=",            min_passes,
            "MinimumConvergedPasses:=",   1,
            "PercentRefinement:=",        30,
            "DeltaS:=",                   delta_s,
            "IsEnabled:=",                1,   # HFSS 19.5 COM: 用整数而不是 bool
            "BasisOrder:=",               1,
        ])
        return HfssResult(ok=True, message=f"已创建求解设置 {setup_name}（{freq_ghz}GHz）")
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def create_frequency_sweep(
    setup_name: str = "Setup1",
    sweep_name: str = "Sweep1",
    start_ghz: float = 1.0,
    stop_ghz: float = 3.0,
    step_ghz: float = 0.01,
    sweep_type: str = "Fast",
) -> HfssResult:
    """创建频率扫描。sweep_type: Fast / Discrete / Interpolating。

    若同名 Sweep 已存在，先删除再重建。
    """
    module = hfss.get_design().GetModule("AnalysisSetup")
    try:
        # 若同名 Sweep 已存在，先删除（避免 COM ERROR_PATH_NOT_FOUND）
        try:
            existing_sweeps = module.GetSweeps(setup_name)
            if sweep_name in (existing_sweeps or []):
                module.DeleteSweep(setup_name, sweep_name)
        except Exception:
            pass  # GetSweeps 不可用时忽略

        module.InsertFrequencySweep(
            setup_name,
            ["NAME:" + sweep_name,
             "IsEnabled:=",   1,
             "RangeType:=",   "LinearStep",
             "RangeStart:=",  f"{start_ghz}GHz",
             "RangeEnd:=",    f"{stop_ghz}GHz",
             "RangeStep:=",   f"{step_ghz}GHz",
             "Type:=",        sweep_type,
             "SaveFields:=",  0,
             "SaveRadFields:=", 0],
        )
        return HfssResult(ok=True,
                          message=f"已创建频率扫描 {sweep_name} ({start_ghz}-{stop_ghz}GHz, {sweep_type})")
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def run_simulation(setup_name: str = "Setup1") -> HfssResult:
    """启动仿真，阻塞直到完成（由上层 Agent 在专用 COM 线程中调用）。"""
    try:
        hfss.get_design().Analyze(setup_name)
        return HfssResult(ok=True, message="仿真完成", data={"setup": setup_name})
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def get_convergence_info(setup_name: str = "Setup1") -> dict:
    """返回最新收敛信息：pass 数、当前 delta S、是否收敛。"""
    module = hfss.get_design().GetModule("AnalysisSetup")
    try:
        info = module.GetSolveRangeInfo(setup_name)
        return {"converged": True, "passes": info}
    except Exception as e:
        return {"converged": False, "error": str(e)}


def update_setup(
    setup_name: str,
    delta_s: float | None = None,
    max_passes: int | None = None,
) -> HfssResult:
    """调整已有求解设置的收敛参数（用于 Agent 自动重试）。"""
    module = hfss.get_design().GetModule("AnalysisSetup")
    try:
        edits: list = []
        if delta_s is not None:
            edits += ["DeltaS:=", delta_s]
        if max_passes is not None:
            edits += ["MaximumPasses:=", max_passes]
        module.EditSetup(setup_name, ["NAME:" + setup_name] + edits)
        return HfssResult(ok=True, message=f"已更新设置 {setup_name}")
    except Exception as e:
        return HfssResult(ok=False, message=str(e))
