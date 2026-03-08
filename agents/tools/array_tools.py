"""阵列设计 LangChain 工具集。"""
import json
from langchain.tools import tool


@tool
def compute_array_weights(params: str) -> str:
    """
    计算线阵方向图权重（幅度 + 相位）并返回阵列因子方向图。

    params 字段：
    - n_elements:    阵元数量（≥ 2）
    - spacing_lambda: 阵元间距（单位：波长，典型 0.5）
    - algorithm:      加权算法（默认 "uniform"）
        • "uniform"   — 均匀加权
        • "chebyshev" — Chebyshev 低旁瓣
        • "taylor"    — Taylor One-parameter
        • "cosine"    — 余弦加权
        • "hamming"   — Hamming 窗
        • "binomial"  — 二项式（零旁瓣）
    - sidelobe_db:   目标旁瓣电平（dB，负值，chebyshev/taylor 有效，默认 -25）
    - steering_deg:  波束指向角（°，默认 0.0）

    返回：amplitudes（归一化）、phases_deg、
          af_data.theta_deg、af_data.AF_dB。
    """
    from backend.hfss.array_design import compute_array_weights as _fn
    p = json.loads(params)
    try:
        data = _fn(**p)  # returns plain dict
        return json.dumps({"ok": True, "message": "权重计算成功", "data": data}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)


@tool
def apply_array_excitation(params: str) -> str:
    """
    将预先计算的幅度/相位权重写入 HFSS 端口变量，实现阵列激励。

    params 字段：
    - phase_deg:    各端口相位列表（°），长度 = 端口数
    - amplitude:    各端口幅度列表（归一化），长度 = 端口数
    - port_prefix:  端口变量名前缀（默认 "Port"）

    HFSS 端口变量命名规则：Port1_A, Port1_P, Port2_A, Port2_P, ...
    """
    from backend.hfss.array_design import apply_array_excitation as _fn
    p = json.loads(params)
    try:
        data = _fn(**p)  # returns plain dict {port_name: {amplitude, phase_deg}}
        return json.dumps({"ok": True, "message": "阵列激励已写入", "data": data}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)
