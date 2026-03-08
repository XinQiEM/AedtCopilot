"""
SessionManager：管理 HFSS COM 连接生命周期与任务队列。

关键约束：win32com 对象绑定创建线程，FastAPI 异步处理器必须通过
run_com() 将所有 COM 调用卸载至专用单线程执行器，严禁在 async def 中
直接调用任何 COM 方法。
"""
from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from backend.hfss.com_client import HfssClient

# 全局专用 COM 线程池（max_workers=1 保证单线程串行，避免 COM 线程竞争）
_com_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="com_worker")


class SessionManager:
    _client: HfssClient | None = None
    _job_store: dict[str, dict] = {}

    @classmethod
    def initialize(cls) -> None:
        """应用启动时调用：连接 HFSS COM（需 HFSS 已运行）。"""
        from backend.hfss.com_client import hfss
        cls._client = hfss
        try:
            hfss.connect()
        except ConnectionError as e:
            import logging
            logging.getLogger(__name__).warning(f"HFSS COM 连接失败（将在首次请求时重试）: {e}")

    @classmethod
    def cleanup(cls) -> None:
        """应用关闭时调用。"""
        _com_executor.shutdown(wait=False)

    @classmethod
    async def run_com(cls, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """在专用 COM 线程中执行阻塞 COM 操作，返回 awaitable。"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _com_executor, lambda: func(*args, **kwargs)
        )

    # ------------------------------------------------------------------
    # 任务状态管理（供长时间仿真轮询使用）
    # ------------------------------------------------------------------

    @classmethod
    def new_job(cls) -> str:
        job_id = str(uuid.uuid4())
        cls._job_store[job_id] = {"status": "running", "result": None, "error": None}
        return job_id

    @classmethod
    def complete_job(cls, job_id: str, result: dict) -> None:
        if job_id in cls._job_store:
            cls._job_store[job_id].update({"status": "done", "result": result})

    @classmethod
    def fail_job(cls, job_id: str, error: str) -> None:
        if job_id in cls._job_store:
            cls._job_store[job_id].update({"status": "error", "error": error})

    @classmethod
    def get_job(cls, job_id: str) -> dict:
        return cls._job_store.get(job_id, {"status": "not_found"})
