from dataclasses import dataclass, field
from typing import List

from backend.hfss.com_client import hfss


@dataclass
class HfssResult:
    """统一返回结构：所有 COM 操作均返回此类型。"""
    ok: bool
    message: str
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 基础几何体
# ---------------------------------------------------------------------------

def create_box(
    origin: List[float],
    sizes: List[float],
    name: str = "Box1",
    material: str = "vacuum",
    unit: str = "mm",
) -> HfssResult:
    """创建长方体。origin=[x,y,z], sizes=[dx,dy,dz]（单位 mm）。"""
    try:
        editor = hfss.get_editor()
        editor.CreateBox(
            ["NAME:BoxParameters",
             "XPosition:=", f"{origin[0]}{unit}",
             "YPosition:=", f"{origin[1]}{unit}",
             "ZPosition:=", f"{origin[2]}{unit}",
             "XSize:=",     f"{sizes[0]}{unit}",
             "YSize:=",     f"{sizes[1]}{unit}",
             "ZSize:=",     f"{sizes[2]}{unit}"],
            ["NAME:Attributes", "Name:=", name],
        )
        # Assign material after creation (MaterialValue:= in CreateBox fails in HFSS 19.5 via COM)
        if material and material.lower() != "vacuum":
            assign_material(name, material)
        return HfssResult(ok=True, message=f"已创建长方体 {name}", data={"name": name})
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def create_cylinder(
    center: List[float],
    radius: float,
    height: float,
    axis: str = "Z",
    name: str = "Cylinder1",
    material: str = "vacuum",
    unit: str = "mm",
) -> HfssResult:
    """创建圆柱体。center=[x,y,z]，axis 可选 X/Y/Z。"""
    try:
        editor = hfss.get_editor()
        editor.CreateCylinder(
            ["NAME:CylinderParameters",
             "XCenter:=",    f"{center[0]}{unit}",
             "YCenter:=",    f"{center[1]}{unit}",
             "ZCenter:=",    f"{center[2]}{unit}",
             "Radius:=",     f"{radius}{unit}",
             "Height:=",     f"{height}{unit}",
             "WhichAxis:=",  axis,
             "NumSides:=",   0],
            ["NAME:Attributes", "Name:=", name],
        )
        if material and material.lower() != "vacuum":
            assign_material(name, material)
        return HfssResult(ok=True, message=f"已创建圆柱体 {name}", data={"name": name})
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def create_sphere(
    center: List[float],
    radius: float,
    name: str = "Sphere1",
    material: str = "vacuum",
    unit: str = "mm",
) -> HfssResult:
    """创建球体。center=[x,y,z]。"""
    try:
        editor = hfss.get_editor()
        editor.CreateSphere(
            ["NAME:SphereParameters",
             "XCenter:=", f"{center[0]}{unit}",
             "YCenter:=", f"{center[1]}{unit}",
             "ZCenter:=", f"{center[2]}{unit}",
             "Radius:=",  f"{radius}{unit}"],
            ["NAME:Attributes", "Name:=", name],
        )
        if material and material.lower() != "vacuum":
            assign_material(name, material)
        return HfssResult(ok=True, message=f"已创建球体 {name}", data={"name": name})
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


# ---------------------------------------------------------------------------
# 布尔运算与对象管理
# ---------------------------------------------------------------------------

def subtract(
    blank: str,
    tools: List[str],
    keep_originals: bool = False,
) -> HfssResult:
    """从 blank 对象中减去 tools 中所有对象。"""
    try:
        editor = hfss.get_editor()
        editor.Subtract(
            ["NAME:Selections",
             "Blank Parts:=", blank,
             "Tool Parts:=",  ",".join(tools)],
            ["NAME:SubtractParameters",
             "KeepOriginals:=", 1 if keep_originals else 0],  # HFSS 19.5 COM: 用整数
        )
        return HfssResult(ok=True, message=f"布尔相减完成 ({blank} - {tools})")
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def unite(obj_list: List[str]) -> HfssResult:
    """合并多个对象为一个实体。"""
    try:
        editor = hfss.get_editor()
        editor.Unite(
            ["NAME:Selections", "Selections:=", ",".join(obj_list)],
            ["NAME:UniteParameters", "KeepOriginals:=", 0],  # HFSS 19.5 COM: 用整数
        )
        return HfssResult(ok=True, message=f"已合并对象: {obj_list}")
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def assign_material(obj_name: str, material: str) -> HfssResult:
    """为已有几何对象指定材料。"""
    try:
        editor = hfss.get_editor()
        editor.AssignMaterial(
            ["NAME:Selections", "Selections:=", obj_name],
            ["NAME:Attributes", "MaterialValue:=", f'"{material}"'],
        )
        return HfssResult(ok=True, message=f"{obj_name} 材料已设为 {material}")
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def list_objects() -> HfssResult:
    """列出当前设计中的所有实体对象名称。"""
    try:
        editor = hfss.get_editor()
        objs = list(editor.GetObjectsInGroup("Solids"))
        return HfssResult(ok=True, message=f"共 {len(objs)} 个实体", data={"objects": objs})
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def delete_object(obj_name: str) -> HfssResult:
    """删除指定名称的几何对象。"""
    try:
        editor = hfss.get_editor()
        editor.Delete(["NAME:Selections", "Selections:=", obj_name])
        return HfssResult(ok=True, message=f"已删除 {obj_name}")
    except Exception as e:
        return HfssResult(ok=False, message=str(e))


def import_cad(file_path: str, heal: bool = True) -> HfssResult:
    """导入 CAD 文件（.step / .sat / .iges）。"""
    try:
        editor = hfss.get_editor()
        editor.Import(
            ["NAME:NativeBodyParameters",
             "HealOption:=", 1 if heal else 0,
             "CheckModel:=", True,
             "TessellationMaxAngle:=", "30deg",
             "ImportFreeSurfaces:=",   False,
             "GroupByAssembly:=",      False,
             "CreateGroup:=",          True,
             "SkipInvisible:=",        False,
             "ApplyFileSettings:=",    False,
             "ApplyDisplaySettings:=", False,
             "ApplyLamination:=",      False,
             "SourceFile:=",           file_path],
        )
        return HfssResult(ok=True, message=f"已导入 CAD: {file_path}", data={"path": file_path})
    except Exception as e:
        return HfssResult(ok=False, message=str(e))

