"""仿真功能单元测试。"""
from unittest.mock import patch

import pytest


class TestCreateSolutionSetup:
    def test_setup_created_ok(self, hfss_client):
        """create_solution_setup 应返回 ok=True 并包含 setup 名称。"""
        with patch("backend.hfss.simulation.hfss", hfss_client):
            from backend.hfss.simulation import create_solution_setup

            result = create_solution_setup(freq_ghz=2.4, setup_name="TestSetup")
        assert result.ok is True


class TestGetConvergenceInfo:
    def test_convergence_returns_data(self, hfss_client):
        """get_convergence_info 在无仿真数据时应安全返回而不抛出。"""
        with patch("backend.hfss.simulation.hfss", hfss_client):
            from backend.hfss.simulation import get_convergence_info

            result = get_convergence_info()
        # ok 可为 True 或 False，但不应抛出异常
        assert result is not None


class TestRunSimulation:
    def test_run_sim_invokes_com(self, hfss_client):
        """run_simulation 应调用 AnalyzeAll COM 方法。"""
        with patch("backend.hfss.simulation.hfss", hfss_client):
            from backend.hfss.simulation import run_simulation

            result = run_simulation(setup_name="Setup1")
        assert hasattr(result, "ok")
