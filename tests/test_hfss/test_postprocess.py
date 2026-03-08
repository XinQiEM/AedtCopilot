"""后处理功能单元测试。"""
import csv
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(path: str, rows: list[dict]) -> None:
    """写一个最小 HFSS-style CSV 供 _parse_csv 解析。"""
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# _parse_csv
# ---------------------------------------------------------------------------

class TestParseCsv:
    def test_parses_frequency_rows(self, tmp_path):
        """频率列（Hz 量级 > 1e6）应除以 1e9 转为 GHz。"""
        csv_file = str(tmp_path / "test_sp.csv")
        _write_csv(csv_file, [
            {"Freq [Hz]": "1000000000", "dB(S(1,1))": "-10.5"},
            {"Freq [Hz]": "2000000000", "dB(S(1,1))": "-12.3"},
        ])
        from backend.hfss.postprocess import _parse_csv
        result = _parse_csv(csv_file)
        assert result["freq_ghz"] == pytest.approx([1.0, 2.0])
        assert "dB(S(1,1))" in result["traces"]
        assert result["traces"]["dB(S(1,1))"] == pytest.approx([-10.5, -12.3])

    def test_parses_angle_rows(self, tmp_path):
        """角度列（值 < 1e6）不做 GHz 转换。"""
        csv_file = str(tmp_path / "test_ff.csv")
        _write_csv(csv_file, [
            {"Theta [deg]": "0",  "GainTotal": "5.2"},
            {"Theta [deg]": "90", "GainTotal": "3.1"},
        ])
        from backend.hfss.postprocess import _parse_csv
        result = _parse_csv(csv_file)
        assert result["freq_ghz"] == pytest.approx([0.0, 90.0])

    def test_missing_file_returns_error_key(self, tmp_path):
        """文件不存在时应返回含 error 键的字典，不抛异常。"""
        from backend.hfss.postprocess import _parse_csv
        result = _parse_csv(str(tmp_path / "nonexistent.csv"))
        assert "error" in result


# ---------------------------------------------------------------------------
# get_s_parameters
# ---------------------------------------------------------------------------

class TestGetSParameters:
    def test_returns_ok_false_on_com_error(self, hfss_client):
        """COM 调用失败时应返回 ok=False 并包含错误消息。"""
        bad_design = MagicMock()
        bad_design.GetModule.side_effect = Exception("COM Error")
        with (
            patch("backend.hfss.postprocess.hfss", hfss_client),
            patch.object(hfss_client, "get_design", return_value=bad_design),
        ):
            from backend.hfss.postprocess import get_s_parameters
            result = get_s_parameters()
        assert result.ok is False
        assert result.message

    def test_returns_ok_with_mock_csv(self, hfss_client, tmp_path):
        """ExportToFile 写 CSV 后 get_s_parameters 应解析出 freq_ghz 和 traces。"""
        csv_path = str(tmp_path / "_tmp_sp.csv")

        def fake_export(report_name, path):
            _write_csv(path, [
                {"Freq [Hz]": "2400000000", "dB(S(1,1))": "-15.0"},
                {"Freq [Hz]": "2450000000", "dB(S(1,1))": "-20.3"},
            ])

        mock_module = MagicMock()
        mock_module.ExportToFile.side_effect = fake_export

        mock_design = MagicMock()
        mock_design.GetModule.return_value = mock_module

        with (
            patch("backend.hfss.postprocess.hfss", hfss_client),
            patch.object(hfss_client, "get_design", return_value=mock_design),
            patch("os.path.join", return_value=csv_path),
        ):
            from backend.hfss.postprocess import get_s_parameters
            result = get_s_parameters()

        assert result.ok is True
        data = result.data
        assert "freq_ghz" in data
        assert len(data["freq_ghz"]) == 2
        assert data["freq_ghz"][0] == pytest.approx(2.4)


# ---------------------------------------------------------------------------
# get_vswr
# ---------------------------------------------------------------------------

class TestGetVswr:
    def test_vswr_delegates_to_get_s_parameters(self, hfss_client):
        """get_vswr 委托给 get_s_parameters，COM 错误时 ok=False。"""
        bad_design = MagicMock()
        bad_design.GetModule.side_effect = Exception("no module")
        with (
            patch("backend.hfss.postprocess.hfss", hfss_client),
            patch.object(hfss_client, "get_design", return_value=bad_design),
        ):
            from backend.hfss.postprocess import get_vswr
            result = get_vswr()
        assert result.ok is False


# ---------------------------------------------------------------------------
# get_far_field
# ---------------------------------------------------------------------------

class TestGetFarField:
    def test_returns_ok_false_on_com_error(self, hfss_client):
        """COM 模块获取失败应安全返回 ok=False。"""
        bad_design = MagicMock()
        bad_design.GetModule.side_effect = RuntimeError("No far-field sphere")
        with (
            patch("backend.hfss.postprocess.hfss", hfss_client),
            patch.object(hfss_client, "get_design", return_value=bad_design),
        ):
            from backend.hfss.postprocess import get_far_field
            result = get_far_field()
        assert result.ok is False

    def test_returns_ok_with_mock_csv(self, hfss_client, tmp_path):
        """模拟远场 CSV 导出后 get_far_field 应返回 theta_deg 和 gain_dbi。"""
        csv_path = str(tmp_path / "_tmp_ff.csv")

        def fake_export(report_name, path):
            _write_csv(path, [
                {"Theta [deg]": "0",  "GainTotal": "6.0"},
                {"Theta [deg]": "90", "GainTotal": "2.5"},
            ])

        mock_module = MagicMock()
        mock_module.ExportToFile.side_effect = fake_export

        mock_design = MagicMock()
        mock_design.GetModule.return_value = mock_module

        with (
            patch("backend.hfss.postprocess.hfss", hfss_client),
            patch.object(hfss_client, "get_design", return_value=mock_design),
            patch("os.path.join", return_value=csv_path),
        ):
            from backend.hfss.postprocess import get_far_field
            result = get_far_field()

        assert result.ok is True
        assert "theta_deg" in result.data
        assert "gain_dbi" in result.data
        assert len(result.data["theta_deg"]) == 2
