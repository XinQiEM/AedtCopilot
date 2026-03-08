"""
conftest.py — Agent 集成测试 Fixture

使用 MagicMock 模拟 win32com 和 LLM，避免真实 HFSS/API 调用。
"""
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage


@pytest.fixture(autouse=True)
def mock_win32com(monkeypatch):
    """阻止 win32com 在无 HFSS 环境中的 import 失败。"""
    # Mock pythoncom first to prevent pywintypes.__import_pywin32_system_module__ error
    monkeypatch.setitem(sys.modules, "pythoncom", MagicMock())
    monkeypatch.setitem(sys.modules, "pywintypes", MagicMock())
    win32com_mock = MagicMock()
    win32com_mock.client.Dispatch.return_value = MagicMock()
    monkeypatch.setitem(sys.modules, "win32com", win32com_mock)
    monkeypatch.setitem(sys.modules, "win32com.client", win32com_mock.client)
    yield win32com_mock


@pytest.fixture
def fake_llm(monkeypatch):
    """
    注入一个确定性假 LLM，避免真实 API 调用。
    每次 invoke 返回固定 AIMessage。
    """
    fake = MagicMock()
    fake.invoke.return_value = AIMessage(content="geometry")
    monkeypatch.setattr("backend.llm_factory.build_llm", lambda *a, **kw: fake)
    return fake


@pytest.fixture
def fake_executor():
    """返回一个预设输出的 AgentExecutor mock（支持 ainvoke 异步调用）。"""
    executor = MagicMock()
    executor.invoke.return_value = {"output": "操作执行成功。"}
    executor.ainvoke = AsyncMock(return_value={"output": "操作执行成功。"})
    return executor
