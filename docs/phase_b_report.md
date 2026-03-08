# 阶段 B 执行结果报告

**项目**：AedtCopilot — 本地 HFSS 智能助手  
**阶段**：B — RAG 知识库 + 流式对话  
**日期**：2025-07-15  
**状态**：✅ 代码完整落地  ❌ 向量索引待建（API Key 未配置）

---

## 1. 阶段目标

| 目标 | 说明 |
|------|------|
| 向量知识库 | 将 HFSS 官方帮助文档（PDF）切片、Embedding 后存入 ChromaDB |
| 检索增强生成 | 每次对话先用问题检索相关文档片段，注入 Agent System Prompt |
| 流式对话接口 | WebSocket `/ws/chat` 实时推送 `intent / rag / token / done / error` 事件 |
| 优雅降级 | 向量库不存在时系统正常启动，RAG 静默跳过 |

---

## 2. 环境与依赖

### 2.1 Python 环境

```
Python 3.12.4
虚拟环境：.venv  (项目根目录)
```

### 2.2 Phase B 新增包

| 包 | 版本 | 用途 |
|----|------|------|
| langchain-chroma | 1.1.0 | ChromaDB LangChain 集成 |
| langchain-text-splitters | 1.1.1 | RecursiveCharacterTextSplitter |
| langchain-community | 0.4.1 | 社区工具集 |

安装命令：

```powershell
.venv\Scripts\pip.exe install langchain-chroma langchain-text-splitters langchain-community
```

### 2.3 HFSS 帮助文档

帮助文档目录：`D:\Program Files\AnsysEM\AnsysEM19.5\Win64\Help\HFSS\`

| 文件 | 大小 | 用途 |
|------|------|------|
| HFSSScriptingGuide.pdf | 7.4 MB | HFSS 脚本 API 参考（首选索引目标） |
| HFSS.pdf | 115 MB | HFSS 完整用户手册 |

---

## 3. 代码变更清单

### 3.1 `backend/config.py` — 新增 Embedding 配置字段

```python
# Phase B 新增
embedding_model: str = "text-embedding-v3"
embedding_api_key: str = ""
embedding_base_url: Optional[str] = None
embedding_batch_size: int = 25
```

- `model_config` 保留 `"extra": "ignore"` 避免 `.env` 多余键报错
- Embedding API Key 独立于 LLM API Key，支持不同服务商

### 3.2 `backend/rag/build_index.py` — 全新实现（Phase A 为桩代码）

**核心常量**

```python
COLLECTION_NAME  = "hfss_docs"
CHUNK_SIZE       = 800
CHUNK_OVERLAP    = 150
DEFAULT_BATCH    = 25
PERSIST_DIR      = "./data/chromadb"
MAX_DISTANCE     = 0.7
```

**主要函数**

| 函数 | 职责 |
|------|------|
| `_iter_pdf_pages(path)` | 逐页提取 PDF 文本（pypdf） |
| `_clean_text(text)` | 去除页码、合并连字符换行 |
| `_build_embeddings()` | 读取 config，构造 `OpenAIEmbeddings`（兼容 DashScope base_url） |
| `_get_or_create_vectorstore(emb)` | 打开或新建 Chroma PersistentClient |
| `index_pdf(path, vs, emb, batch_size, force)` | 分批写入向量库（批间 sleep 0.5s） |
| `build_index(pdf_paths, force)` | 增量索引入口（按文件名去重） |

**文档分割策略**

```python
RecursiveCharacterTextSplitter(
    chunk_size      = 800,
    chunk_overlap   = 150,
    separators      = ["\n\n", "\n", ".", " ", ""]
)
```

**CLI 用法**

```powershell
# 索引脚本参考手册（推荐起点）
.venv\Scripts\python.exe -m backend.rag.build_index \
    --pdfs "D:\Program Files\AnsysEM\AnsysEM19.5\Win64\Help\HFSS\HFSSScriptingGuide.pdf" \
    --batch_size 20

# 追加索引完整用户手册（可选，耗时较长）
.venv\Scripts\python.exe -m backend.rag.build_index \
    --pdfs "D:\Program Files\AnsysEM\AnsysEM19.5\Win64\Help\HFSS\HFSS.pdf" \
    --batch_size 20

# 强制重建
.venv\Scripts\python.exe -m backend.rag.build_index --force
```

### 3.3 `backend/rag/retriever.py` — 全新实现

**类 `HfssRetriever`**

| 方法 | 说明 |
|------|------|
| `init()` | 静默初始化；向量库不存在则 `ready=False`，不抛异常 |
| `query(text, top_k=5)` | `similarity_search_with_relevance_scores`，按 `MAX_DISTANCE=0.7` 过滤 |
| `format_context(results, max_chars=3000)` | 拼接文档片段，返回 LLM 注入字符串（含来源/页码） |
| `get_stats()` | 返回 `{"ready": bool, "chunks": int}` |

**全局单例**：`get_retriever()` 返回进程内唯一实例

### 3.4 `backend/main.py` — Phase B 重要变更

| 变更点 | 内容 |
|--------|------|
| `lifespan` 启动钩子 | 调用 `get_retriever().init()`，日志输出 ready/degraded |
| `GET /health` | 新增 `rag_ready`、`rag_chunks` 字段 |
| `GET /rag/stats` | 直接返回 `get_retriever().get_stats()` |
| `POST /rag/rebuild` | 触发后台异步重建任务 |
| `WebSocket /ws/chat` | 接受 `{"message", "history": [{"role","content"}]}`，推送事件流 |

### 3.5 `agents/orchestrator.py` — RAG 节点 + 流式生成器

**AppState 新增字段**

```python
rag_context: str | None
```

**新增 `fetch_rag_context` 节点**（图的入口节点）

```python
async def fetch_rag_context(state: AppState) -> AppState:
    results = get_retriever().query(state["message"])
    context = get_retriever().format_context(results)
    return {**state, "rag_context": context}
```

**图结构**

```
fetch_rag → classify → geometry | simulation | postprocess | array | general
```

**`stream_chat()` 异步生成器**

```python
async def stream_chat(message: str, history: list[dict]) -> AsyncGenerator[dict, None]:
    # 产出事件：
    # {"type":"intent", "content":"geometry"}
    # {"type":"rag",    "content":"...文档片段..."}
    # {"type":"token",  "content":"字"}    ← LLM 流式输出
    # {"type":"done",   "content":""}
    # {"type":"error",  "content":"..."}
```

事件来源：`astream_events(version="v2")`

### 3.6 子 Agent 改造（geometry / postprocess / array）

三个 Agent 均增加相同改造：

```python
def _build_executor(rag_context: str | None = None):
    system_prompt = BASE_PROMPT
    if rag_context:
        system_prompt += f"\n\n# HFSS 文档参考\n{rag_context}"
    ...

def get_executor(rag_context: str | None = None):
    if rag_context:  # 有 RAG 上下文时绕过缓存，动态构建
        return _build_executor(rag_context)
    ...

def run(state: AppState):
    executor = get_executor(state.get("rag_context"))
    ...
```

### 3.7 `.env` — 新增 Embedding 配置

```ini
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_API_KEY=your_embedding_api_key_here
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_BATCH_SIZE=25
```

---

## 4. 测试结果

### 4.1 依赖安装验证

```powershell
.venv\Scripts\python.exe -c "
import chromadb, langchain_chroma, langchain_text_splitters, langchain_community
from backend.rag.build_index import build_index, COLLECTION_NAME, CHUNK_SIZE, CHUNK_OVERLAP
from backend.rag.retriever import HfssRetriever, get_retriever
print('All Phase B imports OK')
"
```

**结果**：`All Phase B imports OK` ✅

### 4.2 配置常量验证

```
build_index constants: hfss_docs 800 150 25
```

✅ `COLLECTION_NAME=hfss_docs`, `CHUNK_SIZE=800`, `CHUNK_OVERLAP=150`, `DEFAULT_BATCH=25`

### 4.3 Retriever 初始化（无索引状态）

```
retriever stats: {'ready': False, 'chunks': 0}
```

✅ 优雅降级正常：无索引时 `ready=False`，无异常抛出

### 4.4 FastAPI 服务端点

| 端点 | HTTP | 响应 | 状态 |
|------|------|------|------|
| `/health` | 200 OK | `{"hfss_connected":true,"version":"2019.3.0","llm_provider":"openai_compatible","llm_model":"qwen-plus","rag_ready":false,"rag_chunks":0}` | ✅ |
| `/rag/stats` | 200 OK | `{"ready":false,"chunks":0}` | ✅ |
| `/rag/rebuild` | 202 Accepted | `{"message":"rebuild started"}` | ✅ |

### 4.5 索引构建尝试（受阻）

```
openai.AuthenticationError: Error code: 401 - invalid_api_key
```

**原因**：`.env` 中 `EMBEDDING_API_KEY=your_embedding_api_key_here` 为占位符  
**解决方案**：见第 5 节

---

## 5. 待完成事项

### 5.1 【必须】配置真实 API Key

编辑 `.env` 文件：

```ini
# 替换以下两行为真实密钥
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxx      # DashScope API Key（用于 qwen-plus）
EMBEDDING_API_KEY=sk-xxxxxxxxxxxxxxxxxx  # DashScope API Key（可与 LLM 共用同一个）
```

### 5.2 【必须】构建向量索引

```powershell
cd "d:\Xin\GitCopilot\AedtCopilot"

# 第一步：索引脚本参考手册（7.4 MB，约 5-10 分钟）
.venv\Scripts\python.exe -m backend.rag.build_index `
    --pdfs "D:\Program Files\AnsysEM\AnsysEM19.5\Win64\Help\HFSS\HFSSScriptingGuide.pdf" `
    --batch_size 20

# 第二步（可选）：追加完整用户手册（115 MB，耗时较长）
.venv\Scripts\python.exe -m backend.rag.build_index `
    --pdfs "D:\Program Files\AnsysEM\AnsysEM19.5\Win64\Help\HFSS\HFSS.pdf" `
    --batch_size 20
```

### 5.3 【验证】索引后检查

```powershell
# 启动服务
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload

# 检查 /health —— 期望 "rag_ready":true, "rag_chunks":N
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json
```

### 5.4 【可选】WebSocket 流式对话端到端测试

向量索引建立后，可用 wscat 或 Postman 验证：

```json
// 发送
{"message": "如何在 HFSS 脚本中创建矩形面片？", "history": []}

// 期望收到事件序列
{"type":"intent",  "content":"geometry"}
{"type":"rag",     "content":"...HFSSScriptingGuide 相关片段..."}
{"type":"token",   "content":"您"}
{"type":"token",   "content":"可以"}
...
{"type":"done",    "content":""}
```

---

## 6. 阶段 B 文件变更汇总

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/rag/build_index.py` | PDF 索引构建（完整实现） |
| `backend/rag/retriever.py` | 向量检索器（完整实现） |
| `data/chromadb/` | ChromaDB 持久化目录（索引后自动创建） |

### 修改文件

| 文件 | 主要变更 |
|------|---------|
| `backend/config.py` | 新增 4 个 embedding 配置字段 |
| `backend/main.py` | lifespan RAG init, /rag/stats, /rag/rebuild, WebSocket 流式 |
| `agents/orchestrator.py` | AppState.rag_context, fetch_rag 节点, stream_chat 生成器 |
| `agents/geometry_agent.py` | RAG 上下文注入 |
| `agents/postprocess_agent.py` | RAG 上下文注入 |
| `agents/array_agent.py` | RAG 上下文注入 |
| `.env` | 新增 EMBEDDING_* 配置项 |

---

## 7. 架构回顾

```
用户问题
    │
    ▼
WebSocket /ws/chat
    │
    ▼
stream_chat() [orchestrator]
    │
    ├─ [1] fetch_rag_context
    │       │
    │       ├─ HfssRetriever.query(question, top_k=5)
    │       │       │
    │       │       └─ ChromaDB similarity_search (MAX_DISTANCE=0.7)
    │       │
    │       └─ format_context() → rag_context 字符串
    │               └─ 推送 {"type":"rag", ...} 事件
    │
    ├─ [2] classify
    │       └─ 判断意图 → geometry / simulation / postprocess / array / general
    │               └─ 推送 {"type":"intent", ...} 事件
    │
    └─ [3] 子 Agent
            │
            ├─ System Prompt + rag_context 注入
            ├─ LLM 流式生成（astream_events v2）
            └─ 推送 {"type":"token", ...} × N + {"type":"done"}
```

---

## 8. 下一阶段预览（Phase C）

| 任务 | 技术栈 |
|------|--------|
| 前端聊天界面 | Next.js 15 + shadcn/ui |
| 流式渲染 | WebSocket → React state streaming |
| HFSS 状态面板 | 显示当前设计名称、参数、仿真状态 |
| 代码高亮 | react-syntax-highlighter |
| 对话历史 | localStorage 持久化 |

---

*本文档由 GitHub Copilot 自动生成，记录 AedtCopilot 阶段 B 执行过程与结果。*
