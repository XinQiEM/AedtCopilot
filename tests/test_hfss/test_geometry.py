"""几何功能单元测试。"""
import json
from unittest.mock import MagicMock, patch

import pytest


class TestCreateBox:
    def test_create_box_returns_ok(self, hfss_client):
        """create_box 在 COM 调用成功时应返回 ok=True。"""
        with patch("backend.hfss.geometry.hfss", hfss_client):
            from backend.hfss.geometry import create_box

            result = create_box(
                origin=[0, 0, 0],
                sizes=[10, 5, 2],
                name="Patch",
                material="pec",
            )
        assert result.ok is True
        assert "Patch" in result.message or result.message  # 有消息

    def test_create_box_bad_sizes_raises(self, hfss_client):
        """COM 报错时应捕获异常并返回 ok=False。"""
        hfss_client.get_editor().CreateBox = MagicMock(side_effect=Exception("COM Error"))
        with patch("backend.hfss.geometry.hfss", hfss_client):
            from backend.hfss.geometry import create_box

            result = create_box(origin=[0, 0, 0], sizes=[10, 5, 2], name="Err")
        assert result.ok is False


class TestListObjects:
    def test_list_returns_names(self, hfss_client):
        """list_objects 应返回对象列表数据。"""
        with patch("backend.hfss.geometry.hfss", hfss_client):
            from backend.hfss.geometry import list_objects

            result = list_objects()
        assert result.ok is True
        # data 为包含 objects 键的字典或直接为列表
        objects = result.data.get("objects") if isinstance(result.data, dict) else result.data
        assert isinstance(objects, list)


class TestAssignMaterial:
    def test_assign_material_ok(self, hfss_client):
        with patch("backend.hfss.geometry.hfss", hfss_client):
            from backend.hfss.geometry import assign_material

            result = assign_material(obj_name="Patch", material="Rogers 4003C")
        assert result.ok is True
