"""
RAG 检索器 — 从 ChromaDB 向量库中召回与用户提问最相关的 HFSS 文档片段。

在 backend.main 的 lifespan 中调用 get_retriever().init()，
之后可在 Agent / Orchestrator 中直接使用。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

COLLECTION_NAME = "hfss_docs"
DEFAULT_TOP_K = 5

# 相似度距离阈值：distance > MAX_DISTANCE 的结果将被过滤（1 - cos_sim）
MAX_DISTANCE = 0.7


class HfssRetriever:
    """
    HFSS 文档向量检索器。

    生命周期：
        retriever = HfssRetriever()
        retriever.init()          # 启动时调用（如向量库不存在则静默降级）
        results = retriever.query("how to create lumped port")
    """

    def __init__(self) -> None:
        self._vectorstore = None
        self._ready = False

    # ─── 初始化 ───────────────────────────────────────────────────────────

    def init(self) -> bool:
        """
        尝试连接本地 ChromaDB 向量库。
        成功返回 True；向量库不存在或为空时返回 False（降级为无 RAG 模式）。
        """
        try:
            from langchain_chroma import Chroma
            from backend.config import settings

            persist_dir = str(Path(settings.chromadb_path).resolve())
            if not Path(persist_dir).exists():
                logger.info("RAG: 向量库目录不存在 (%s)，降级为无 RAG 模式", persist_dir)
                return False

            if settings.embedding_provider == "local":
                from langchain_huggingface import HuggingFaceEmbeddings
                embeddings = HuggingFaceEmbeddings(
                    model_name=settings.embedding_model,
                    model_kwargs={"device": "cpu"},
                    encode_kwargs={"normalize_embeddings": True},
                )
            else:
                from langchain_openai import OpenAIEmbeddings
                api_key = settings.embedding_api_key or settings.llm_api_key
                base_url = settings.embedding_base_url or settings.llm_base_url
                emb_kwargs: dict = {"model": settings.embedding_model, "api_key": api_key}
                if base_url:
                    emb_kwargs["base_url"] = base_url
                embeddings = OpenAIEmbeddings(**emb_kwargs)

            self._vectorstore = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=embeddings,
                persist_directory=persist_dir,
            )

            # 检查集合是否有内容
            count = self._vectorstore._collection.count()
            if count == 0:
                logger.info("RAG: 向量库为空，请先运行 build_index.py，当前降级为无 RAG 模式")
                self._vectorstore = None
                return False

            self._ready = True
            logger.info("RAG: 向量库就绪，共 %d 个 chunks（%s）", count, persist_dir)
            return True

        except Exception as exc:
            logger.warning("RAG: 初始化失败（%s），降级为无 RAG 模式", exc)
            self._vectorstore = None
            self._ready = False
            return False

    # ─── 检索 ─────────────────────────────────────────────────────────────

    def query(self, text: str, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
        """
        返回与 text 最相关的文档片段列表（按相似度降序）。

        每项格式：
            {
                "text":   str,    # 文档片段内容
                "source": str,    # PDF 文件名
                "page":   int,    # 来源页码
                "score":  float,  # 相似度（0-1，越高越相关）
            }

        向量库未就绪时返回空列表（降级）。
        """
        if not self._ready or self._vectorstore is None:
            return []

        try:
            results = self._vectorstore.similarity_search_with_relevance_scores(
                text, k=top_k
            )
            output = []
            for doc, score in results:
                if score < (1.0 - MAX_DISTANCE):
                    continue
                output.append({
                    "text": doc.page_content,
                    "source": doc.metadata.get("source", "未知"),
                    "page": doc.metadata.get("page", 0),
                    "score": round(float(score), 4),
                })
            return output
        except Exception as exc:
            logger.warning("RAG 检索出错（%s），返回空结果", exc)
            return []

    # ─── 格式化 ───────────────────────────────────────────────────────────

    def format_context(self, results: list[dict[str, Any]], max_chars: int = 3000) -> str:
        """
        将检索结果格式化为可注入 LLM System Prompt 的上下文字符串。

        Args:
            results:   query() 的返回值
            max_chars: 总字符上限（防止超出 context window）
        """
        if not results:
            return ""

        lines = ["=== HFSS 参考文档（来自官方手册）==="]
        total = 0
        for i, r in enumerate(results, 1):
            header = f"[{i}] {r['source']} 第 {r['page']} 页（相关度 {r['score']:.2f}）"
            chunk_text = r["text"].strip()
            entry = f"{header}\n{chunk_text}\n"
            if total + len(entry) > max_chars:
                lines.append(f"[{i}] ...（内容过长，已截断）")
                break
            lines.append(entry)
            total += len(entry)
        lines.append("================================")
        return "\n".join(lines)

    @property
    def is_ready(self) -> bool:
        return self._ready

    def get_stats(self) -> dict[str, Any]:
        """返回向量库统计信息。"""
        if not self._ready or self._vectorstore is None:
            return {"ready": False, "chunks": 0}
        try:
            count = self._vectorstore._collection.count()
            return {"ready": True, "chunks": count}
        except Exception:
            return {"ready": self._ready, "chunks": -1}


# ─── 全局单例 ────────────────────────────────────────────────────────────────

_retriever: HfssRetriever | None = None


def get_retriever() -> HfssRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HfssRetriever()
    return _retriever
