"""
validate_com.py — HFSS COM 接口连通性验证脚本

在运行主服务前执行此脚本，确认：
  1. pywin32 可正常导入
  2. HFSS ProgID 已注册
  3. 能成功连接 HFSS（需提前打开 HFSS 软件）

用法：
    python docs/validate_com.py
    python docs/validate_com.py --progid "AnsoftHfss.HfssScriptInterface"
"""
from __future__ import annotations

import argparse
import sys
import traceback

PROGID = "AnsoftHfss.HfssScriptInterface"
SEPARATOR = "-" * 60


def step(msg: str) -> None:
    print(f"\n{'='*3} {msg}")


def ok(detail: str = "") -> None:
    print(f"  ✅ OK  {detail}")


def fail(detail: str = "") -> None:
    print(f"  ❌ FAIL  {detail}")


def check_pywin32() -> bool:
    step("检查 pywin32 是否安装")
    try:
        import win32com.client  # noqa: F401
        import pywintypes       # noqa: F401
        ok("win32com.client 导入成功")
        return True
    except ImportError as e:
        fail(str(e))
        print("  提示: pip install pywin32 后运行 python Scripts/pywin32_postinstall.py -install")
        return False


def check_progid_registry(progid: str) -> bool:
    step(f"检查 COM ProgID 注册表: {progid}")
    try:
        import winreg
        key_path = f"SOFTWARE\\Classes\\{progid}"
        winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        ok(f"HKLM\\{key_path} 存在")
        return True
    except FileNotFoundError:
        fail(f"注册表键不存在（HFSS 是否已安装？）")
        return False
    except Exception as e:
        fail(str(e))
        return False


def check_dispatch(progid: str) -> bool:
    step(f"尝试 win32com.client.Dispatch('{progid}')")
    try:
        import win32com.client
        app = win32com.client.Dispatch(progid)
        ver = getattr(app, "GetVersion", lambda: "N/A")()
        ok(f"连接成功 | Version = {ver}")
        return True
    except Exception as e:
        fail(str(e))
        print("  提示: 请先启动 Ansys HFSS 2019 R3，再运行本脚本")
        return False


def check_project_list(progid: str) -> bool:
    step("列出已打开的 HFSS 项目")
    try:
        import win32com.client
        app = win32com.client.Dispatch(progid)
        oDesktop = app.GetAppDesktop()
        projects = oDesktop.GetProjects()
        if projects:
            ok(f"共 {len(projects)} 个项目: {[p.GetName() for p in projects]}")
        else:
            ok("HFSS 已连接，但当前无打开的项目（请打开一个设计后再测试）")
        return True
    except Exception as e:
        fail(str(e))
        traceback.print_exc()
        return False


def main(progid: str) -> int:
    print(SEPARATOR)
    print("AedtCopilot — HFSS COM 接口验证")
    print(SEPARATOR)

    results = [
        check_pywin32(),
        check_progid_registry(progid),
        check_dispatch(progid),
        check_project_list(progid),
    ]

    print(f"\n{SEPARATOR}")
    passed = sum(results)
    total = len(results)
    if passed == total:
        print(f"✅ 全部 {total} 项检查通过，COM 接口正常！")
        return 0
    else:
        print(f"⚠️  {total - passed}/{total} 项检查失败，请根据提示排查。")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HFSS COM 接口连通性验证")
    parser.add_argument("--progid", default=PROGID, help=f"COM ProgID (默认: {PROGID})")
    args = parser.parse_args()
    sys.exit(main(args.progid))
