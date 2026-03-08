"""后处理 LangChain 工具集。"""
import json
from langchain.tools import tool


@tool
def get_s_parameters(params: str) -> str:
    """
    提取 S 参数（回波损耗/传输系数）数据。

    params 字段：
    - ports:       端口数量（默认 1）
    - setup_sweep: "Setup1:Sweep1" 格式（默认 "Setup1:Sweep1"）

    返回频率数组与 S 参数矩阵（dB）。
    """
    from backend.hfss.postprocess import get_s_parameters as _fn
    p = json.loads(params) if params.strip() else {}
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message, "data": r.data}, ensure_ascii=False)


@tool
def get_vswr(params: str = "{}") -> str:
    """
    计算并返回 VSWR（电压驻波比）随频率的变化数据。

    params 字段：
    - port_index:  端口索引，从 1 开始（默认 1）
    - setup_sweep: "Setup1:Sweep1"（默认 "Setup1:Sweep1"）
    """
    from backend.hfss.postprocess import get_vswr as _fn
    p = json.loads(params) if params.strip() else {}
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message, "data": r.data}, ensure_ascii=False)


@tool
def get_far_field(params: str = "{}") -> str:
    """
    获取远场辐射方向图数据（增益/指向性）。

    params 字段（均可选）：
    - phi_deg:     方位角 Phi（°，默认 0）
    - freq_ghz:    频率（GHz，默认取第一个求解频率）
    - setup_sweep: "Setup1:LastAdaptive"（默认）

    返回 theta（°）、Gain_dBi、Directivity_dBi 数组。
    """
    from backend.hfss.postprocess import get_far_field as _fn
    p = json.loads(params) if params.strip() else {}
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message, "data": r.data}, ensure_ascii=False)
