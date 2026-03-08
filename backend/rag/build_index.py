"""
RAG 知识库构建脚本 — 将 HFSS 文档 PDF 解析、分块、嵌入后写入 ChromaDB。

用法（命令行）：
    # 索引单个或多个 PDF
    python -m backend.rag.build_index --pdfs "D:/Help/HFSS/HFSSScriptingGuide.pdf"

    # 索引整个目录下的所有 PDF
    python -m backend.rag.build_index --docs_dir "D:/Help/HFSS"

    # 强制重建（清空再索引）
    python -m backend.rag.build_index --docs_dir "D:/Help/HFSS" --reset

特性：
    - 按 PDF 文件名做增量索引（已索引的文件默认跳过）
    - 每批 25 个 chunk 调用一次 Embedding API（避免超限）
    - 支持 OpenAI / Azure / openai_compatible 三类 Embedding 端点
    - 写入 ChromaDB PersistentClient，后续可离线检索
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import time
from pathlib import Path
from typing import Iterator

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# ─── 默认常量（可由 Settings 覆盖）─────────────────────────────────────────
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 150
DEFAULT_BATCH_SIZE = 25   # 每次调用 Embedding API 的 chunk 数
COLLECTION_NAME = "hfss_docs"


# ─── 工具函数 ───────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """清理 PDF 提取的原始文本：合并断词、去除多余空行。"""
    # 去除页码行（纯数字行）
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)
    # 合并同一句子被换行分断的情况（行末无句号且下一行首字母小写）
    text = re.sub(r"(?<![.!?])\n(?=[a-z])", " ", text)
    # 压缩多个空行为最多两个
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _iter_pdf_pages(pdf_path: Path) -> Iterator[tuple[int, str]]:
    """逐页提取 PDF 文本，yield (page_number, text)。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("请先安装 pypdf：pip install pypdf")

    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    logger.info("  解析 %s（%d 页）", pdf_path.name, total)
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            yield i + 1, _clean_text(text)


def _build_embeddings():
    """根据 Settings 构建 LangChain Embeddings 实例。

    支持两种模式：
      embedding_provider="local"   → HuggingFaceEmbeddings（本地，无需 API Key）
      embedding_provider="openai"  → OpenAIEmbeddings（可兼容任意 OpenAI-兼容接口）
    """
    from backend.config import settings

    if settings.embedding_provider == "local":
        from langchain_huggingface import HuggingFaceEmbeddings
        logger.info("使用本地 Embedding 模型: %s", settings.embedding_model)
        return HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    # OpenAI / openai_compatible
    from langchain_openai import OpenAIEmbeddings
    api_key = settings.embedding_api_key or settings.llm_api_key
    base_url = settings.embedding_base_url or settings.llm_base_url
    kwargs: dict = {"model": settings.embedding_model, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAIEmbeddings(**kwargs)


def _get_or_create_vectorstore(embeddings, reset: bool = False):
    """打开（或重建）ChromaDB 向量库。"""
    from langchain_chroma import Chroma
    from backend.config import settings

    persist_dir = str(Path(settings.chromadb_path).resolve())
    if reset:
        import shutil
        if Path(persist_dir).exists():
            shutil.rmtree(persist_dir)
            logger.info("已清空旧向量库 %s", persist_dir)

    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=persist_dir,
    )


def _get_indexed_sources(vectorstore) -> set[str]:
    """返回已索引的 PDF 源文件名集合。"""
    try:
        result = vectorstore.get(include=["metadatas"])
        sources = {m.get("source", "") for m in (result.get("metadatas") or [])}
        return {s for s in sources if s}
    except Exception:
        return set()


def index_pdf(
    pdf_path: Path,
    vectorstore,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """
    索引单个 PDF 文件。
    返回写入的 chunk 数量。
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    all_docs: list[Document] = []
    for page_num, page_text in _iter_pdf_pages(pdf_path):
        chunks = splitter.split_text(page_text)
        for i, chunk in enumerate(chunks):
            all_docs.append(Document(
                page_content=chunk,
                metadata={
                    "source": pdf_path.name,
                    "source_path": str(pdf_path),
                    "page": page_num,
                    "chunk_index": i,
                },
            ))

    if not all_docs:
        logger.warning("  %s：未提取到任何文本，跳过。", pdf_path.name)
        return 0

    logger.info("  %s：%d chunks，分 %d 批写入向量库…",
                pdf_path.name, len(all_docs),
                (len(all_docs) + batch_size - 1) // batch_size)

    written = 0
    for start in range(0, len(all_docs), batch_size):
        batch = all_docs[start: start + batch_size]
        vectorstore.add_documents(batch)
        written += len(batch)
        logger.info("    进度 %d / %d chunks", written, len(all_docs))
        # 保护性 sleep：仅对 API 接口生效，本地模型无需等待
        from backend.config import settings
        if settings.embedding_provider != "local" and start + batch_size < len(all_docs):
            time.sleep(0.5)

    return written


def build_index(
    pdf_paths: list[Path],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    batch_size: int = DEFAULT_BATCH_SIZE,
    reset: bool = False,
    skip_existing: bool = True,
) -> dict[str, int]:
    """
    构建/更新 HFSS RAG 知识库索引。

    Args:
        pdf_paths:     要索引的 PDF 文件路径列表
        chunk_size:    每个文本块的最大字符数（默认 800）
        chunk_overlap: 相邻块的重叠字符数（默认 150）
        batch_size:    每批 Embedding API 调用的 chunk 数（默认 25）
        reset:         True = 清空现有向量库后重建
        skip_existing: True = 跳过已索引过的 PDF（按源文件名判断）

    Returns:
        {"indexed": n_new_files, "skipped": n_skipped, "total_chunks": n_chunks}
    """
    if not pdf_paths:
        raise ValueError("未指定任何 PDF 文件。")

    logger.info("=== 构建 HFSS 知识库索引 ===")
    logger.info("PDF 数量: %d", len(pdf_paths))

    embeddings = _build_embeddings()
    vectorstore = _get_or_create_vectorstore(embeddings, reset=reset)

    already_indexed = _get_indexed_sources(vectorstore) if skip_existing else set()
    if already_indexed:
        logger.info("检测到已索引文件: %s", already_indexed)

    stats = {"indexed": 0, "skipped": 0, "total_chunks": 0}
    for pdf_path in pdf_paths:
        if not pdf_path.exists():
            logger.error("文件不存在，跳过: %s", pdf_path)
            continue
        if skip_existing and pdf_path.name in already_indexed:
            logger.info("  [跳过] %s（已索引）", pdf_path.name)
            stats["skipped"] += 1
            continue
        logger.info("[索引] %s (%.1f MB)", pdf_path.name,
                    pdf_path.stat().st_size / 1024 / 1024)
        n = index_pdf(pdf_path, vectorstore, chunk_size, chunk_overlap, batch_size)
        stats["total_chunks"] += n
        stats["indexed"] += 1

    logger.info("=== 索引完成：%d 个文件，共 %d chunks，跳过 %d 个文件 ===",
                stats["indexed"], stats["total_chunks"], stats["skipped"])
    return stats


# ─── 命令行入口 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # 默认索引 HFSS 安装目录中的两个核心文档
    DEFAULT_HELP_DIR = r"D:\Program Files\AnsysEM\AnsysEM19.5\Win64\Help\HFSS"

    parser = argparse.ArgumentParser(description="构建 HFSS RAG 知识库索引")
    parser.add_argument(
        "--pdfs", nargs="+",
        help="要索引的 PDF 文件路径列表（空格分隔）",
    )
    parser.add_argument(
        "--docs_dir", default=None,
        help="PDF 目录路径，目录下所有 .pdf 均会被索引",
    )
    parser.add_argument("--chunk_size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk_overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    parser.add_argument("--batch_size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--reset", action="store_true",
                        help="清空已有向量库后重新索引")
    parser.add_argument("--no_skip", action="store_true",
                        help="强制重新索引（即使已存在）")
    args = parser.parse_args()

    # 收集 PDF 路径
    pdf_list: list[Path] = []
    if args.pdfs:
        pdf_list.extend(Path(p) for p in args.pdfs)
    if args.docs_dir:
        d = Path(args.docs_dir)
        pdf_list.extend(sorted(d.glob("*.pdf")))
    if not pdf_list:
        # 默认策略：优先索引 Scripting Guide（最相关），再索引主手册
        default_dir = Path(DEFAULT_HELP_DIR)
        scripting = default_dir / "HFSSScriptingGuide.pdf"
        main_doc = default_dir / "HFSS.pdf"
        if scripting.exists():
            pdf_list.append(scripting)
        if main_doc.exists():
            pdf_list.append(main_doc)

    build_index(
        pdf_paths=pdf_list,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        batch_size=args.batch_size,
        reset=args.reset,
        skip_existing=not args.no_skip,
    )
