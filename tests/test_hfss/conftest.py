"""
conftest.py — HFSS 单元测试通用 Fixture

使用 MagicMock 模拟 win32com COM 对象，让测试无需真实 HFSS。
"""
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_win32com(monkeypatch):
    """自动注入 win32com.client mock，防止 import 失败。"""
    # Mock pythoncom before importing com_client to avoid pywin32 load failure
    pythoncom_mock = MagicMock()
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom_mock)
    monkeypatch.setitem(sys.modules, "pywintypes", MagicMock())

    win32com_mock = MagicMock()
    win32com_mock.client.Dispatch.return_value = _make_hfss_mock()
    monkeypatch.setitem(sys.modules, "win32com", win32com_mock)
    monkeypatch.setitem(sys.modules, "win32com.client", win32com_mock.client)
    yield win32com_mock


def _make_hfss_mock() -> MagicMock:
    """构建模拟 HFSS COM 对象树。"""
    app = MagicMock()
    desktop = MagicMock()
    project = MagicMock()
    design = MagicMock()
    editor = MagicMock()

    app.GetAppDesktop.return_value = desktop
    desktop.GetActiveProject.return_value = project
    desktop.GetProjects.return_value = [project]
    project.GetName.return_value = "MockProject"
    project.GetActiveDesign.return_value = design
    project.GetDesigns.return_value = [design]
    design.GetName.return_value = "MockDesign"
    design.SetDesignSettings = MagicMock()
    design.GetModule.return_value = editor
    editor.GetMatchedObjectName.return_value = ["Box1", "Ground", "Substrate"]
    editor.GetObjectName.return_value = "Box1"

    return app


@pytest.fixture
def hfss_client(mock_win32com):
    """返回已连接的 HfssClient 实例（使用 mock COM）。"""
    # 重置单例以便每次测试得到干净实例
    from backend.hfss import com_client
    com_client._instance = None
    client = com_client.HfssClient()
    client.connect()
    return client
