"""仿真控制 LangChain 工具集。"""
import json
from langchain.tools import tool


@tool
def assign_radiation_boundary(params: str = "{}") -> str:
    """
    为指定 HFSS 对象分配辐射边界条件（Radiation Boundary）。

    params 字段（均可选）：
    - obj_names:     需要指定辐射边界的对象名列表，例如 ["Region"] 或 ["Box1"]
                     不填时默认使用 ["Region"]（HFSS 标准空气盒名称）
    - boundary_name: 边界名称（默认 "Rad1"）

    典型用法：
    - 用户说空气盒/Region 加辐射边界：params = "{}"
    - 用户说给 Box1 加辐射边界：params = '{"obj_names": ["Box1"]}'
    - 用户说给立方体/盒子加辐射边界：先调用 list_objects 获取对象名，再传入
    """
    from backend.hfss.simulation import assign_radiation_boundary as _fn
    p = json.loads(params) if params.strip() else {}
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message}, ensure_ascii=False)


@tool
def assign_lumped_port(params: str) -> str:
    """
    在指定矩形面上创建 Lumped Port 激励。

    params 字段：
    - face_id:    面 ID（int）
    - impedance:  端口阻抗（Ω，默认 50.0）
    - port_name:  端口名称（可选，默认 "Port1"）
    """
    from backend.hfss.simulation import assign_lumped_port as _fn
    p = json.loads(params)
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message}, ensure_ascii=False)


@tool
def create_solution_setup(params: str) -> str:
    """
    创建或更新 HFSS Solution Setup（求解配置）。

    params 字段：
    - freq_ghz:          求解频率（GHz）
    - setup_name:        Setup 名称（可选，默认 "Setup1"）
    - max_passes:        最大自适应迭代次数（默认 10）
    - max_delta_s:       S 参数收敛阈值（默认 0.02）
    - percent_error:     最大误差百分比（默认 2.0）
    """
    from backend.hfss.simulation import create_solution_setup as _fn
    p = json.loads(params)
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message, "data": r.data}, ensure_ascii=False)


@tool
def create_frequency_sweep(params: str) -> str:
    """
    在已有的 Setup 上创建频率扫描（Sweep）。

    params 字段：
    - setup_name:   Setup 名称（默认 "Setup1"）
    - start_ghz:    起始频率（GHz）
    - stop_ghz:     终止频率（GHz）
    - step_ghz:     步进（GHz，默认 0.1）
    - sweep_name:   Sweep 名称（可选，默认 "Sweep1"）
    - sweep_type:   "Interpolating" | "Fast" | "Discrete"（默认 "Interpolating"）
    """
    from backend.hfss.simulation import create_frequency_sweep as _fn
    p = json.loads(params)
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message, "data": r.data}, ensure_ascii=False)


@tool
def run_simulation(params: str = "{}") -> str:
    """
    提交 HFSS 仿真任务并等待收敛（同步阻塞）。

    params 字段（可选）：
    - setup_name:   Setup 名称（默认 "Setup1"）
    - num_cores:    使用核心数（默认 4）
    返回是否收敛及收敛信息。
    """
    from backend.hfss.simulation import run_simulation as _fn
    p = json.loads(params) if params.strip() else {}
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message, "data": r.data}, ensure_ascii=False)


@tool
def get_convergence_info(params: str = "{}") -> str:
    """
    获取最近一次仿真的收敛信息（每次迭代的 ΔS 和 mesh 数）。

    params 字段（可选）：
    - setup_name: Setup 名称（默认 "Setup1"）
    """
    from backend.hfss.simulation import get_convergence_info as _fn
    p = json.loads(params) if params.strip() else {}
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "data": r.data}, ensure_ascii=False)


@tool
def assign_plane_wave(params: str) -> str:
    """
    在 HFSS 当前设计中设置平面波激励（Incident Wave / Plane Wave）。

    params 字段：
    - freq_mhz:     频率（MHz，例如 300）
    - theta_deg:    入射角 θ（相对 Z 轴，单位度，例如 90）
    - phi_deg:      方位角 φ（从 X 轴起，单位度，例如 0）
    - wave_name:    激励名称（可选，默认 "PlaneWave1"）
    - polarization: "linear_v"（θ/垂直极化，默认）或 "linear_h"（φ/水平极化）

    示例：{"freq_mhz": 300, "theta_deg": 90, "phi_deg": 0}
    """
    from backend.hfss.simulation import assign_plane_wave as _fn
    p = json.loads(params)
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message}, ensure_ascii=False)
