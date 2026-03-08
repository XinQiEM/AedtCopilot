import os
import threading
import win32com.client
import pythoncom
from backend.config import settings


class HfssClient:
    """HFSS COM 连接单例，管理 oDesktop/oProject/oDesign 层级。"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connected = False
        return cls._instance

    def connect(self) -> None:
        """连接到已运行的 HFSS 实例（需先手动打开 HFSS）。"""
        try:
            # COM 初始化：确保当前线程已注册 COM 单元，支持跨线程调用
            pythoncom.CoInitialize()
            self.oApp = win32com.client.Dispatch(settings.hfss_com_progid)
            self.oDesktop = self.oApp.GetAppDesktop()
            self._connected = True
            self._com_thread_id = threading.get_ident()
        except Exception as e:
            raise ConnectionError(f"无法连接 HFSS COM: {e}") from e

    def ensure_project(
        self,
        save_path: str | None = None,
        design_name: str = "HFSSDesign1",
    ) -> None:
        """确保有一个可用的 HFSS 项目+设计。

        若已有活动项目和设计，不做任何事。
        否则创建新项目，保存到 save_path（HFSS 19.5 需要先保存才能操作），
        插入 HFSS DrivenModal 设计，并激活它。
        """
        desktop = self._get_desktop()
        self._ensure_project_with(desktop, save_path=save_path, design_name=design_name)

    def get_project(self, name: str | None = None):
        """获取当前激活项目，可选指定项目名。"""
        desktop = self._get_desktop()
        if name:
            desktop.SetActiveProject(name)
        return desktop.GetActiveProject()

    def get_design(self, project=None, name: str | None = None):
        """获取当前激活设计，可选指定设计名。"""
        proj = project or self.get_project()
        if name:
            proj.SetActiveDesign(name)
        design = proj.GetActiveDesign()
        return design

    def _get_desktop(self):
        """获取当前线程的 oDesktop 代理（避免跨 COM 单元问题）。

        对于 EXE 进程外服务器，每个线程应通过 Dispatch() 重新获取代理，
        而不是跨 COM 单元共享缓存的代理对象。
        """
        pythoncom.CoInitialize()
        app = win32com.client.Dispatch(settings.hfss_com_progid)
        return app.GetAppDesktop()

    def get_editor(self, design=None):
        """获取 3D Modeler 几何编辑器。若无活动项目则自动创建。"""
        if design is None:
            # 确保有活动项目+设计，避免 GetActiveProject 失败
            try:
                self.ensure_project()
            except Exception:
                pass  # 若仍失败，下面会抛出明确错误
        d = design or self.get_design()
        return d.SetActiveEditor("3D Modeler")

    def _ensure_project_with(self, desktop, save_path=None, design_name="HFSSDesign1"):
        """用给定 desktop 代理确保有活动项目+设计。"""
        try:
            proj = desktop.GetActiveProject()
            if proj is not None:
                design = proj.GetActiveDesign()
                if design is not None:
                    return
        except Exception:
            pass

        oProj = desktop.NewProject()
        if save_path is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
            os.makedirs(data_dir, exist_ok=True)
            save_path = os.path.join(data_dir, "HfssSession.aedt")
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except Exception:
                pass
        oProj.SaveAs(save_path, True)
        oProj.InsertDesign("HFSS", design_name, "DrivenModal", "")
        oProj.SetActiveDesign(design_name)

    def _get_design_with(self, desktop, name=None):
        """用给定 desktop 代理获取当前激活设计。"""
        proj = desktop.GetActiveProject()
        if name:
            proj.SetActiveDesign(name)
        return proj.GetActiveDesign()

    def list_projects(self) -> list[str]:
        """列出所有已打开的项目名称。"""
        try:
            return list(self._get_desktop().GetProjects())
        except Exception:
            return []

    def list_designs(self) -> list[str]:
        """列出当前项目的所有设计名称。"""
        try:
            proj = self.get_project()
            return list(proj.GetDesigns())
        except Exception:
            return []

    def close_all_projects(self) -> None:
        """关闭所有打开的项目（脚本清理用）。"""
        try:
            for p in list(self._get_desktop().GetProjects()):
                try:
                    p.Close()
                except Exception:
                    pass
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_version(self) -> str:
        """返回 HFSS 版本字符串。"""
        try:
            return str(self._get_desktop().GetVersion())
        except Exception:
            return "AEDT 19.5"


# 全局单例
hfss = HfssClient()
