"""
FastAPI 应用入口。
启动命令：uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import settings
from backend.session import SessionManager
from backend.llm_factory import build_llm, invalidate_llm_cache

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化 HFSS COM 会话
    SessionManager.initialize()
    # 初始化 RAG 检索器（向量库不存在时静默降级）
    from backend.rag.retriever import get_retriever
    rag_ready = get_retriever().init()
    if rag_ready:
        logger.info("RAG 就绪，已加载向量库")
    else:
        logger.info("RAG 未就绪，运行 build_index.py 后将自动开启")
    yield
    SessionManager.cleanup()


app = FastAPI(title="AedtCopilot API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    client = SessionManager._client
    connected = client.is_connected if client else False
    version = client.get_version() if connected else "N/A"
    from backend.rag.retriever import get_retriever
    rag_stats = get_retriever().get_stats()
    return {
        "hfss_connected": connected,
        "version": version,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "rag_ready": rag_stats.get("ready", False),
        "rag_chunks": rag_stats.get("chunks", 0),
    }


# ---------------------------------------------------------------------------
# LLM 热配置接口
# ---------------------------------------------------------------------------

class LLMConfigRequest(BaseModel):
    provider: str
    api_key: str
    model: str
    base_url: str | None = None
    azure_endpoint: str | None = None
    azure_deployment: str | None = None
    azure_api_version: str = "2024-02-01"
    temperature: float = 0.0
    max_tokens: int = 4096


@app.post("/llm/config")
async def update_llm_config(req: LLMConfigRequest):
    """热切换 LLM 配置（不重启服务）。"""
    settings.llm_provider = req.provider
    settings.llm_api_key = req.api_key
    settings.llm_model = req.model
    if req.base_url is not None:
        settings.llm_base_url = req.base_url
    if req.azure_endpoint is not None:
        settings.azure_endpoint = req.azure_endpoint
    if req.azure_deployment is not None:
        settings.azure_deployment = req.azure_deployment
    settings.azure_api_version = req.azure_api_version
    settings.llm_temperature = req.temperature
    settings.llm_max_tokens = req.max_tokens
    invalidate_llm_cache()
    return {"ok": True, "provider": req.provider, "model": req.model}


@app.post("/llm/test")
async def test_llm_connection(req: LLMConfigRequest):
    """用提交的配置快速测试 LLM 连通性。"""
    import time
    # Temporarily update settings
    old = {k: getattr(settings, k) for k in
           ("llm_provider", "llm_api_key", "llm_model", "llm_base_url",
            "llm_temperature", "llm_max_tokens")}
    settings.llm_provider = req.provider
    settings.llm_api_key = req.api_key
    settings.llm_model = req.model
    if req.base_url is not None:
        settings.llm_base_url = req.base_url
    settings.llm_temperature = req.temperature
    settings.llm_max_tokens = req.max_tokens
    invalidate_llm_cache()
    try:
        t0 = time.monotonic()
        llm = build_llm()
        llm.invoke("Hi")
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"ok": True, "latency_ms": latency_ms}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        for k, v in old.items():
            setattr(settings, k, v)
        invalidate_llm_cache()


@app.get("/rag/stats")
async def rag_stats():
    """RAG 知识库状态。"""
    from backend.rag.retriever import get_retriever
    return get_retriever().get_stats()


@app.post("/rag/rebuild")
async def rag_rebuild(background_tasks=None):
    """
    触发后台重建向量索引（默认文档路径）。
    返回任务所属 job_id；建建过程可通过 /results/{job_id} 查询。
    """
    import asyncio
    from pathlib import Path

    HELP_DIR = Path(settings.hfss_install_path).parent / "Win64" / "Help" / "HFSS"
    if not HELP_DIR.exists():
        HELP_DIR = Path(r"D:\Program Files\AnsysEM\AnsysEM19.5\Win64\Help\HFSS")

    job_id = SessionManager.new_job("rag_rebuild")

    async def _rebuild():
        try:
            from backend.rag.build_index import build_index
            pdfs = list(HELP_DIR.glob("*.pdf"))
            if not pdfs:
                raise FileNotFoundError(f"在 {HELP_DIR} 未找到 PDF")
            stats = build_index(pdf_paths=pdfs, skip_existing=True)
            # 重新加载检索器
            from backend.rag.retriever import _retriever
            import backend.rag.retriever as _r_mod
            _r_mod._retriever = None
            _r_mod.get_retriever().init()
            SessionManager.complete_job(job_id, stats)
        except Exception as exc:
            SessionManager.fail_job(job_id, str(exc))

    asyncio.create_task(_rebuild())
    return {"job_id": job_id, "status": "started"}


# ---------------------------------------------------------------------------
# HFSS 项目 / 设计管理
# ---------------------------------------------------------------------------

@app.get("/projects")
async def list_projects():
    client = SessionManager._client
    if not client or not client.is_connected:
        raise HTTPException(status_code=503, detail="HFSS 未连接")
    names = await SessionManager.run_com(client.list_projects)
    return {"projects": names}


class ProjectOpenRequest(BaseModel):
    path: str

class ProjectNewRequest(BaseModel):
    name: str

@app.post("/projects/open")
async def open_project(req: ProjectOpenRequest):
    await SessionManager.run_com(
        lambda: SessionManager._client.oDesktop.OpenProject(req.path)
    )
    return {"ok": True, "path": req.path}

@app.post("/projects/new")
async def new_project(req: ProjectNewRequest):
    await SessionManager.run_com(
        lambda: SessionManager._client.oDesktop.NewProject()
    )
    return {"ok": True, "name": req.name}


@app.get("/designs")
async def list_designs():
    client = SessionManager._client
    if not client or not client.is_connected:
        raise HTTPException(status_code=503, detail="HFSS 未连接")
    names = await SessionManager.run_com(client.list_designs)
    return {"designs": names}


class DesignActivateRequest(BaseModel):
    name: str

@app.post("/designs/activate")
async def activate_design(req: DesignActivateRequest):
    await SessionManager.run_com(
        lambda: SessionManager._client.get_design(name=req.name)
    )
    return {"ok": True, "name": req.name}


# ---------------------------------------------------------------------------
# 几何对象
# ---------------------------------------------------------------------------

@app.get("/objects")
async def list_objects():
    from backend.hfss.geometry import list_objects as _list
    result = await SessionManager.run_com(_list)
    return result.__dict__

@app.delete("/objects/{name}")
async def delete_object(name: str):
    from backend.hfss.geometry import delete_object as _del
    result = await SessionManager.run_com(_del, name)
    return result.__dict__


# ---------------------------------------------------------------------------
# CAD 上传
# ---------------------------------------------------------------------------

@app.post("/upload-cad")
async def upload_cad(file: UploadFile = File(...)):
    import os, tempfile, shutil
    suffix = os.path.splitext(file.filename or "model.step")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    from backend.hfss.geometry import import_cad
    result = await SessionManager.run_com(import_cad, tmp_path)
    os.unlink(tmp_path)
    return result.__dict__


# ---------------------------------------------------------------------------
# 任务状态查询
# ---------------------------------------------------------------------------

@app.get("/results/{job_id}")
async def get_result(job_id: str):
    return SessionManager.get_job(job_id)


# ---------------------------------------------------------------------------
# LLM 配置管理
# ---------------------------------------------------------------------------

class LLMConfigRequest(BaseModel):
    provider: str
    api_key: str
    model: str
    base_url: str | None = None
    azure_endpoint: str | None = None
    azure_deployment: str | None = None
    azure_api_version: str = "2024-02-01"
    temperature: float = 0.0
    max_tokens: int = 4096
    streaming: bool = True


@app.get("/llm/config")
async def get_llm_config():
    key = settings.llm_api_key
    masked = (key[:4] + "****" + key[-4:]) if len(key) > 8 else "****"
    return {
        "provider":    settings.llm_provider,
        "api_key":     masked,
        "model":       settings.llm_model,
        "base_url":    settings.llm_base_url,
        "temperature": settings.llm_temperature,
        "streaming":   settings.llm_streaming,
    }


@app.post("/llm/config")
async def update_llm_config(req: LLMConfigRequest):
    settings.llm_provider    = req.provider       # type: ignore[assignment]
    settings.llm_api_key     = req.api_key
    settings.llm_model       = req.model
    settings.llm_base_url    = req.base_url
    settings.azure_endpoint  = req.azure_endpoint
    settings.azure_deployment = req.azure_deployment or ""
    settings.azure_api_version = req.azure_api_version
    settings.llm_temperature = req.temperature
    settings.llm_max_tokens  = req.max_tokens
    settings.llm_streaming   = req.streaming
    invalidate_llm_cache()
    return {"ok": True, "message": f"LLM 已切换至 {req.provider} / {req.model}"}


@app.post("/llm/test")
async def test_llm():
    import time
    from langchain_core.messages import HumanMessage
    llm = build_llm()
    t0 = time.perf_counter()
    try:
        resp = await llm.ainvoke([HumanMessage(content="hello")])
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": True, "latency_ms": latency_ms,
                "model": settings.llm_model, "provider": settings.llm_provider}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/llm/providers")
async def list_providers():
    return {"providers": [
        {"value": "openai",            "label": "OpenAI",               "required": ["api_key", "model"]},
        {"value": "azure_openai",      "label": "Azure OpenAI",         "required": ["api_key", "azure_endpoint", "azure_deployment"]},
        {"value": "anthropic",         "label": "Anthropic Claude",     "required": ["api_key", "model"]},
        {"value": "openai_compatible", "label": "OpenAI 兼容接口（国内平台/本地）",
         "required": ["api_key", "model", "base_url"],
         "presets": {
             "魔塔社区 ModelScope": {"base_url": "https://api-inference.modelscope.cn/v1",           "model": "Qwen/Qwen2.5-72B-Instruct"},
             "通义千问 DashScope":  {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1","model": "qwen-max"},
             "Kimi K2.5（旗舰）":   {"base_url": "https://api.moonshot.cn/v1",                       "model": "kimi-k2.5"},
             "Kimi Moonshot":       {"base_url": "https://api.moonshot.cn/v1",                       "model": "moonshot-v1-8k"},
             "MiniMax":             {"base_url": "https://api.minimaxi.com/v1",                      "model": "MiniMax-Text-01"},
             "DeepSeek":            {"base_url": "https://api.deepseek.com/v1",                      "model": "deepseek-chat"},
             "智谱 AI":             {"base_url": "https://open.bigmodel.cn/api/paas/v4",             "model": "glm-4-flash"},
             "百度千帆":             {"base_url": "https://qianfan.baidubce.com/v2",                  "model": "ernie-speed-128k"},
             "本地 Ollama":         {"base_url": "http://localhost:11434/v1",                        "model": "qwen2.5:7b"},
         }},
    ]}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# WebSocket 聊天入口（流式 + RAG + 真实 Agent）
# ---------------------------------------------------------------------------

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """WebSocket 流式对话接口。

    客户端发送 JSON：
        {"message": "...", "session_id": "...", "history": [{"role":"..","content":"..."}]}

    服务端逐步推送：
        {"type": "intent",  "content": "geometry"}
        {"type": "rag",     "content": "已检索 N 条文档"}
        {"type": "token",   "content": "..."}  (逐 token 推送)
        {"type": "done",    "content": ""}
        {"type": "error",   "content": "..."}
    """
    from langchain_core.messages import AIMessage, HumanMessage
    from agents.orchestrator import stream_chat

    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            user_message: str = payload.get("message", "")
            raw_history: list = payload.get("history", [])

            # 将前端传来的历史转换为 LangChain BaseMessage 列表
            history = []
            for item in raw_history:
                role = item.get("role", "user")
                content = item.get("content", "")
                if role == "user":
                    history.append(HumanMessage(content=content))
                else:
                    history.append(AIMessage(content=content))

            # 流式运行 Agent
            async for event in stream_chat(user_message, history):
                await websocket.send_text(json.dumps(event, ensure_ascii=False))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "content": str(e)}))
        except Exception:
            pass
