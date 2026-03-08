"""
conftest.py — HFSS 集成测试 Fixture（需真实 HFSS 进程运行）

运行方式：
  pytest tests/test_integration/ --integration          # 需 HFSS 已启动
  pytest tests/test_integration/ -m "not integration"  # 跳过（仅冒烟）
  HFSS_TEST_LIVE=1 pytest tests/test_integration/      # 通过环境变量启用

所有集成测试自动加 @pytest.mark.integration 标记。
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run tests that require a live HFSS instance",
    )


def pytest_collection_modifyitems(config, items):
    """若未传 --integration，自动跳过所有集成测试。"""
    live = config.getoption("--integration") or os.environ.get("HFSS_TEST_LIVE") == "1"
    if live:
        return
    skip_mark = pytest.mark.skip(reason="需要真实 HFSS（加 --integration 或 HFSS_TEST_LIVE=1）")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_mark)


# ---------------------------------------------------------------------------
# 公共 Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_hfss():
    """
    Session 级别的 HfssClient，连接到已运行的 HFSS 实例。
    若连接失败则 pytest.skip() 整个测试会话。
    """
    try:
        from backend.hfss.com_client import hfss as _hfss_singleton
        # 使用全局单例（geometry/simulation 模块依赖同一实例）
        if not _hfss_singleton.is_connected:
            _hfss_singleton.connect()
        # 确保有可用的 HFSS 项目+设计（HFSS 19.5 需要先保存项目到磁盘）
        _hfss_singleton.ensure_project(
            save_path=r"D:\Xin\GitCopilot\AedtCopilot\data\IntegrationTest.aedt",
            design_name="IntTestDesign",
        )
        # 清理设计中遗留的几何体和 Setup（上次测试留下的残留）
        _clean_design(_hfss_singleton)
        yield _hfss_singleton
    except Exception as exc:
        pytest.skip(f"无法连接 HFSS COM：{exc}")


def _clean_design(hfss_client) -> None:
    """删除设计中所有 3D 对象和分析 Setup，为本次测试提供干净起点。"""
    # 删除所有 3D 几何对象
    try:
        from backend.hfss.geometry import list_objects, delete_object
        r = list_objects()
        for obj in r.data.get("objects", []):
            try:
                delete_object(obj_name=obj)
            except Exception:
                pass
    except Exception:
        pass

    # 删除所有分析 Setup（同时删除其下属的 Sweep）
    try:
        module = hfss_client.get_design().GetModule("AnalysisSetup")
        setups = module.GetSetups()
        if setups:
            module.DeleteSetups(list(setups))
    except Exception:
        pass


@pytest.fixture
def hfss_design(live_hfss):
    """返回当前活动 HFSS design 对象（oDesign）。"""
    return live_hfss.get_design()


@pytest.fixture
def hfss_editor(live_hfss):
    """返回 3D Modeler 几何编辑器。"""
    return live_hfss.get_editor()


@pytest.fixture(autouse=True)
def cleanup_hfss_objects(live_hfss):
    """
    测试前记录已有对象，测试后删除新增几何体，保持 HFSS 环境清洁。
    使用 yield + 后置清理模式。
    """
    from backend.hfss.geometry import list_objects, delete_object
    before = set()
    try:
        r = list_objects()
        before = set(r.data.get("objects", [])) if r.ok else set()
    except Exception:
        pass

    yield  # 执行测试

    try:
        r = list_objects()
        after = set(r.data.get("objects", [])) if r.ok else set()
        new_objects = after - before
        for obj in new_objects:
            try:
                delete_object(obj_name=obj)
            except Exception:
                pass
    except Exception:
        pass
