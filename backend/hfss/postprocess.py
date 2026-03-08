import csv
import os
import time

from backend.hfss.com_client import hfss
from backend.hfss.geometry import HfssResult


def get_s_parameters(
    setup_name: str = "Setup1",
    sweep_name: str = "Sweep1",
    expressions: list[str] | None = None,
) -> HfssResult:
    """
    提取 S 参数，返回 Plotly-ready 数据结构。
    data 结构：{"freq_ghz": [...], "traces": {"dB(S(1,1))": [...]}}
    """
    report_name = f"_tmp_sp_{int(time.time())}"
    exprs = expressions or ["dB(S(1,1))"]
    csv_path = os.path.join(os.environ.get("TEMP", "C:/tmp"), f"{report_name}.csv")
    try:
        module = hfss.get_design().GetModule("ReportSetup")
        module.CreateReport(
            report_name,
            "Modal Solution Data",
            "Rectangular Plot",
            f"{setup_name} : {sweep_name}",
            ["Domain:=", "Sweep"],
            ["Freq:=", ["All"]],
            ["X Component:=", "Freq", "Y Component:=", exprs],
        )
        module.ExportToFile(report_name, csv_path)
        data = _parse_csv(csv_path)
        module.DeleteReports([report_name])
        return HfssResult(ok=True, message="S 参数提取成功", data=data)
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def get_vswr(
    setup_name: str = "Setup1",
    sweep_name: str = "Sweep1",
    port: int = 1,
) -> HfssResult:
    """提取 VSWR。"""
    return get_s_parameters(
        setup_name, sweep_name,
        expressions=[f"VSWR({port})"],
    )


def get_far_field(
    setup_name: str = "Setup1",
    sphere_name: str = "3D",
    phi_deg: float = 0.0,
) -> HfssResult:
    """
    提取远场方向图（GainTotal，phi=固定值，theta 0-180°）。
    data 结构：{"theta_deg": [...], "gain_dbi": [...]}
    """
    report_name = f"_tmp_ff_{int(time.time())}"
    csv_path = os.path.join(os.environ.get("TEMP", "C:/tmp"), f"{report_name}.csv")
    try:
        module = hfss.get_design().GetModule("ReportSetup")
        module.CreateReport(
            report_name,
            "Far Fields",
            "Rectangular Plot",
            f"{setup_name} : LastAdaptive",
            ["Context:=",   sphere_name],
            ["Theta:=",     ["All"],
             "Phi:=",       [f"{phi_deg}deg"],
             "Freq:=",      ["All"]],
            ["X Component:=", "Theta",
             "Y Component:=", ["GainTotal"]],
        )
        module.ExportToFile(report_name, csv_path)
        raw = _parse_csv(csv_path)
        module.DeleteReports([report_name])
        # 重新整理 key
        data = {
            "theta_deg": list(raw.get("freq_ghz", [])),
            "gain_dbi":  list(list(raw.get("traces", {}).values() or [[]])[0]),
        }
        return HfssResult(ok=True, message="方向图提取成功", data=data)
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _parse_csv(path: str) -> dict:
    """
    解析 HFSS 导出 CSV。
    返回：{"freq_ghz": [...], "traces": {"列名": [...]}}
    第一列视为 X 轴（频率/角度）并除以 1e9 转换为 GHz；
    若 X 轴非频率（如 Theta），直接作为原始值存入 freq_ghz 字段（命名保持兼容）。
    """
    result: dict = {"freq_ghz": [], "traces": {}}
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                vals = list(row.items())
                if not vals:
                    continue
                x_val = float(vals[0][1])
                # 频率列（Hz 级别）自动转 GHz；角度列（<1000）不转换
                result["freq_ghz"].append(x_val / 1e9 if x_val > 1e6 else x_val)
                for k, v in vals[1:]:
                    result["traces"].setdefault(k, []).append(float(v))
    except FileNotFoundError:
        result["error"] = f"CSV 文件未生成: {path}"
    return result
