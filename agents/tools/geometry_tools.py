"""几何操作 LangChain 工具集。"""
import json
from langchain.tools import tool


@tool
def create_box(params: str) -> str:
    """
    在 HFSS 中创建长方体（Box）几何体。

    params 为 JSON 字符串，字段：
    - origin:   [x, y, z]   起点坐标（单位 mm）
    - sizes:    [dx, dy, dz] 三轴尺寸（单位 mm）
    - name:     对象名称（可选，默认 "Box1"）
    - material: 材料名称（可选，默认 "vacuum"，PEC 填 "pec"）

    示例: '{"origin":[0,0,0],"sizes":[10,5,2],"name":"Patch","material":"pec"}'
    """
    from backend.hfss.geometry import create_box as _fn
    p = json.loads(params)
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message, "data": r.data}, ensure_ascii=False)


@tool
def create_cylinder(params: str) -> str:
    """
    在 HFSS 中创建圆柱体。

    params 字段：
    - center:   [x, y, z]  圆心坐标（mm）
    - radius:   半径（mm）
    - height:   高度（mm）
    - axis:     轴方向，"X"/"Y"/"Z"（默认 "Z"）
    - name:     对象名称（可选）
    - material: 材料（可选）
    """
    from backend.hfss.geometry import create_cylinder as _fn
    p = json.loads(params)
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message, "data": r.data}, ensure_ascii=False)


@tool
def create_sphere(params: str) -> str:
    """
    在 HFSS 中创建球体。

    params 字段：
    - center: [x, y, z]（mm）
    - radius: 半径（mm）
    - name:   对象名称（可选）
    - material: 材料（可选）
    """
    from backend.hfss.geometry import create_sphere as _fn
    p = json.loads(params)
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message, "data": r.data}, ensure_ascii=False)


@tool
def subtract_objects(params: str) -> str:
    """
    布尔相减：从 blank 对象中减去 tools 列表中的对象。

    params 字段：
    - blank:          被减对象名（str）
    - tools:          工具对象名列表（list[str]）
    - keep_originals: 是否保留工具对象（默认 false）
    """
    from backend.hfss.geometry import subtract as _fn
    p = json.loads(params)
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message}, ensure_ascii=False)


@tool
def assign_material(params: str) -> str:
    """
    为已有几何对象指定材料。

    params 字段：
    - obj_name: 对象名称
    - material: 材料名称（须在 HFSS 材料库中存在）
    """
    from backend.hfss.geometry import assign_material as _fn
    p = json.loads(params)
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message}, ensure_ascii=False)


@tool
def list_objects(params: str = "{}") -> str:
    """
    列出当前 HFSS 设计中的所有实体对象名称。
    params 可为空 JSON "{}"。
    """
    from backend.hfss.geometry import list_objects as _fn
    r = _fn()
    return json.dumps({"ok": r.ok, "message": r.message, "data": r.data}, ensure_ascii=False)


@tool
def delete_object(params: str) -> str:
    """
    删除 HFSS 当前设计中的指定几何对象。

    params 字段：
    - obj_name: 要删除的对象名称（str）

    若不确定对象名称，先调用 list_objects 获取当前设计中的对象列表，再传入。
    示例: '{"obj_name": "Box1"}'
    """
    from backend.hfss.geometry import delete_object as _fn
    p = json.loads(params)
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message}, ensure_ascii=False)


@tool
def import_cad_file(params: str) -> str:
    """
    导入 CAD 文件到 HFSS（支持 .step/.sat/.iges）。

    params 字段：
    - file_path: CAD 文件的绝对路径
    - heal:      是否自动修复模型（默认 true）
    """
    from backend.hfss.geometry import import_cad as _fn
    p = json.loads(params)
    r = _fn(**p)
    return json.dumps({"ok": r.ok, "message": r.message, "data": r.data}, ensure_ascii=False)
