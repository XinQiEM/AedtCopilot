"""
天线阵列加权算法。
支持：uniform / chebyshev / taylor / cosine / hamming / binomial
"""
from __future__ import annotations

import numpy as np


def _binomial_weights(n: int) -> np.ndarray:
    """二项式加权：各阵元幅度正比于组合数 C(n-1, k)。"""
    from math import comb
    return np.array([comb(n - 1, k) for k in range(n)], dtype=float)


def compute_array_weights(
    n_elements: int,
    spacing_lambda: float = 0.5,
    algorithm: str = "chebyshev",
    sidelobe_db: float = -30.0,
    steering_deg: float = 0.0,
) -> dict:
    """
    计算线阵各阵元幅度和相位激励，以及阵列因子方向图。

    参数：
        n_elements:      阵元数
        spacing_lambda:  阵元间距（以波长为单位，默认 0.5λ）
        algorithm:       加权窗算法
                         uniform / chebyshev / taylor / cosine / hamming / binomial
        sidelobe_db:     旁瓣电平（dB，负值，仅 chebyshev/taylor 有效）
        steering_deg:    主瓣扫描角（°，相对于阵列法线）

    返回：
        {
            "amplitudes":  [float, ...],          # 各阵元归一化幅度
            "phases_deg":  [float, ...],          # 各阵元激励相位（°）
            "af_data": {
                "theta_deg": [float, ...],        # -90° ~ +90°
                "AF_dB":     [float, ...],        # 阵列因子（dB）
            },
        }
    """
    from scipy.signal.windows import chebwin, taylor

    funcs: dict = {
        "uniform":   lambda n, sl: np.ones(n),
        "chebyshev": lambda n, sl: chebwin(n, abs(sl)),
        "taylor":    lambda n, sl: taylor(n, nbar=4, sll=abs(sl)),
        "cosine":    lambda n, sl: np.cos(np.linspace(-np.pi / 2, np.pi / 2, n)),
        "hamming":   lambda n, sl: np.hamming(n),
        "binomial":  lambda n, sl: _binomial_weights(n),
    }

    if algorithm not in funcs:
        raise ValueError(f"未知算法 {algorithm}，支持: {list(funcs)}")

    w: np.ndarray = funcs[algorithm](n_elements, sidelobe_db)
    w = w / w.max()

    d = spacing_lambda * 2 * np.pi          # 归一化相位进度
    n_arr = np.arange(n_elements)
    phi = -d * n_arr * np.sin(np.deg2rad(steering_deg))  # 渐进相位

    # 阵列因子
    theta = np.linspace(-90, 90, 1801)
    u = np.sin(np.deg2rad(theta))
    AF = np.abs(
        np.sum(
            w[:, None] * np.exp(1j * (d * n_arr[:, None] * u + phi[:, None])),
            axis=0,
        )
    )
    AF_dB = 20 * np.log10(AF / (AF.max() + 1e-12) + 1e-12)

    return {
        "amplitudes": w.tolist(),
        "phases_deg": np.rad2deg(phi).tolist(),
        "af_data": {
            "theta_deg": theta.tolist(),
            "AF_dB":     AF_dB.tolist(),
        },
    }


def apply_array_excitation(
    phase_deg: list[float],
    amplitude: list[float] | None = None,
    port_prefix: str = "P",
) -> dict:
    """
    将阵列激励写入 HFSS 端口变量（通过参数化变量实现）。
    返回端口名 → 幅度/相位映射，供前端确认展示。
    """
    n = len(phase_deg)
    amp = amplitude or [1.0] * n
    result = {}
    design = None
    try:
        from backend.hfss.com_client import hfss
        design = hfss.get_design()
    except Exception:
        pass  # 联调前允许无 COM 连接

    for i, (a, p) in enumerate(zip(amp, phase_deg)):
        port_name = f"{port_prefix}{i + 1}"
        result[port_name] = {"amplitude": round(a, 6), "phase_deg": round(p, 4)}
        if design:
            try:
                design.SetVariableValue(f"Mag_{port_name}", str(a))
                design.SetVariableValue(f"Phase_{port_name}", f"{p}deg")
            except Exception:
                pass

    return result
