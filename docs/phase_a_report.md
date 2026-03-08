# 阶段 A 执行结果报告

**项目**：AedtCopilot — 本地化 HFSS 智能仿真助手  
**阶段**：Phase A — 基本框架构建  
**执行日期**：2026-03-03  
**执行状态**：✅ 全部完成

---

## 一、目标回顾

阶段 A 的目标是在 `d:\Xin\GitCopilot\AedtCopilot` 目录下从零构建完整的项目骨架，包括：

- Python 虚拟环境及依赖安装
- 后端服务核心模块（FastAPI + HFSS COM 封装）
- 多 LLM Provider 支持（openai / azure_openai / anthropic / openai_compatible）
- LangGraph 多 Agent 编排框架骨架
- RAG 知识库和并行扫描子包桩代码
- 单元测试框架与辅助工具脚本
- 完整的配置与环境文件

---

## 二、执行过程

### 2.1 环境准备

| 步骤 | 操作 | 结果 |
|------|------|------|
| 创建虚拟环境 | `D:\Software\Python3.12\python.exe -m venv .venv` | ✅ Python 3.12.4 venv 创建成功 |
| 修复 requirements.txt 编码 | 重写为纯 ASCII（原文件含中文注释，pip GBK 解码失败） | ✅ 已修复 |
| 安装依赖 | `.venv\Scripts\pip.exe install -r requirements.txt` | ✅ 19 个核心包全部安装完成 |
| pywin32 后处理 | `python pywin32_postinstall.py -install` | ✅ DLL 复制、注册表写入成功 |

**遇到的问题**：`requirements.txt` 含中文注释，pip 在 GBK 系统编码下无法解析（`UnicodeDecodeError: 'gbk' codec`）。解决方案：用 `[System.IO.File]::WriteAllText(..., [System.Text.Encoding]::ASCII)` 重写文件为纯 ASCII。

### 2.2 后端核心模块

| 文件 | 关键内容 |
|------|----------|
| `backend/config.py` | pydantic-settings v2 配置，`LLMProvider` Literal 类型，支持 4 种 Provider，`extra="ignore"` 忽略 `.env` 中多余字段 |
| `backend/llm_factory.py` | `build_llm()` 单例工厂，按 Provider 分发到 ChatOpenAI / AzureChatOpenAI / ChatAnthropic，`openai_compatible` 分支覆盖所有国内平台 |
| `backend/session.py` | `ThreadPoolExecutor(max_workers=1)` 保证 COM 线程安全，`SessionManager` 管理 Job 生命周期 |
| `backend/main.py` | FastAPI lifespan 上下文，`/health`、`/projects`、`/designs`、`/objects`、`/upload-cad`、`/results/{job_id}`、`GET/POST /llm/config`、`POST /llm/test`、`GET /llm/providers`、WebSocket `/ws/chat` 桩 |

**遇到的问题**：`backend/config.py` 底部直接实例化 `Settings()`，而 `.env` 文件中存在 `HFSS_AEDT_VERSION`、`HFSS_INSTALL_DIR`、`HFSS_PROGID`、`SERVER_HOST`、`SERVER_PORT` 等字段名与 Settings 字段名不匹配，导致 pydantic v2 抛出 `Extra inputs are not permitted`。解决方案：在 `model_config` 中加入 `"extra": "ignore"`。

### 2.3 HFSS COM 封装层

| 文件 | 封装内容 |
|------|----------|
| `backend/hfss/com_client.py` | `HfssClient` 单例（`__new__` 模式），`connect()`、`get_project()`、`get_design()`、`get_editor()`、`list_projects()`、`list_designs()`、`get_version()`；全局实例 `hfss = HfssClient()` |
| `backend/hfss/geometry.py` | `HfssResult` dataclass；`create_box`、`create_cylinder`、`create_sphere`、`subtract`、`unite`、`assign_material`、`list_objects`、`delete_object`、`import_cad`（共 9 个函数） |
| `backend/hfss/simulation.py` | `assign_radiation_boundary`、`assign_lumped_port`、`create_solution_setup`、`create_frequency_sweep`、`run_simulation`、`get_convergence_info`、`update_setup`（共 7 个函数） |
| `backend/hfss/postprocess.py` | `get_s_parameters`、`get_vswr`、`get_far_field`、`_parse_csv`（自动识别 Hz/度 轴） |
| `backend/hfss/array_design.py` | `compute_array_weights`（6 种算法：uniform/chebyshev/taylor/cosine/hamming/binomial）、`apply_array_excitation` |

### 2.4 Prompt 模板

`backend/prompts/system_prompts.py` 包含 5 个系统提示：

- `GEOMETRY_SYSTEM_PROMPT` — 几何建模专用
- `SIMULATION_SYSTEM_PROMPT` — 仿真控制专用
- `POSTPROCESS_SYSTEM_PROMPT` — 后处理分析专用
- `ARRAY_SYSTEM_PROMPT` — 阵列设计专用
- `ORCHESTRATOR_SYSTEM_PROMPT` — 顶层意图路由

### 2.5 LangGraph 多 Agent 框架

#### 工具层（`agents/tools/`）

每个工具文件将对应 `backend/hfss/` 模块的函数封装为带 `@tool` 装饰器的 LangChain 工具，参数均通过 JSON 字符串传递：

| 文件 | 包含工具 |
|------|----------|
| `geometry_tools.py` | `create_box`、`create_cylinder`、`create_sphere`、`subtract_objects`、`assign_material`、`list_objects`、`import_cad_file` |
| `simulation_tools.py` | `assign_radiation_boundary`、`assign_lumped_port`、`create_solution_setup`、`create_frequency_sweep`、`run_simulation`、`get_convergence_info` |
| `postprocess_tools.py` | `get_s_parameters`、`get_vswr`、`get_far_field` |
| `array_tools.py` | `compute_array_weights`、`apply_array_excitation` |

#### Agent 层（`agents/`）

| 文件 | 实现方式 | 关键设计 |
|------|----------|----------|
| `orchestrator.py` | LangGraph `StateGraph` | `AppState` 全局状态；`classify_intent` 节点用 LLM 分类意图；条件路由到 4 个子 Agent |
| `geometry_agent.py` | LangChain `create_tool_calling_agent` + `AgentExecutor` | 绑定 7 个几何工具，最多 10 次迭代 |
| `simulation_agent.py` | LangGraph 状态机 | `SimState` 含 `retry_count`/`converged`；未收敛自动降低 `max_delta_s`、增加 `max_passes` 重试，最多 3 次 |
| `postprocess_agent.py` | LangChain `AgentExecutor` | 绑定 3 个后处理工具 |
| `array_agent.py` | LangChain `AgentExecutor` | 绑定 2 个阵列工具 |

### 2.6 RAG 与并行扫描（桩代码）

| 文件 | 说明 |
|------|------|
| `backend/rag/build_index.py` | Phase B 占位；扫描 PDF 目录、分块、嵌入、写入 ChromaDB 的完整接口已定义 |
| `backend/rag/retriever.py` | `HfssRetriever` 单例；`is_ready()` 返回 False（Phase B 前降级为无 RAG 模式） |
| `backend/parallel/scenario_runner.py` | `Scenario` / `SweepConfig` dataclass；`run_sweep()` 支持串行/并行模式，含 `LicenseError` 自动降级串行 |

### 2.7 测试框架

| 文件 | 说明 |
|------|------|
| `tests/test_hfss/conftest.py` | `mock_win32com` (`autouse`) —— 自动注入 MagicMock COM 对象树；`hfss_client` fixture |
| `tests/test_hfss/test_geometry.py` | `TestCreateBox`、`TestListObjects`、`TestAssignMaterial` 各 1-2 个用例 |
| `tests/test_hfss/test_simulation.py` | `TestCreateSolutionSetup`、`TestGetConvergenceInfo`、`TestRunSimulation` |
| `tests/test_agents/conftest.py` | `mock_win32com` + `fake_llm` fixture（避免真实 API 调用） |

### 2.8 辅助工具与配置文件

| 文件 | 说明 |
|------|------|
| `docs/validate_com.py` | 4 步 COM 连通性验证（pywin32 导入→注册表→Dispatch→项目列表），彩色终端输出 |
| `.env` | 已从 `.env.example` 生成，填入占位值；当前激活: `LLM_PROVIDER=openai_compatible`, `LLM_MODEL=qwen-plus`, `LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `data/chromadb/.gitkeep` | 占位文件，追踪 ChromaDB 目录到 Git |
| `requirements.txt` | 纯 ASCII，19 项依赖（已修复 GBK 编码问题） |
| `.gitignore` | 标准 Python + Node.js + HFSS 忽略规则 |

---

## 三、最终目录结构

```
AedtCopilot/
├── .env                          # 本地环境配置（勿提交）
├── .env.example                  # 配置模板
├── .gitignore
├── requirements.txt              # 纯 ASCII，19 项依赖
├── DEVELOPMENT_PLAN.md           # 总体开发规划（Phase A-F）
│
├── backend/
│   ├── __init__.py
│   ├── config.py                 # pydantic-settings 配置中心
│   ├── llm_factory.py            # 多 Provider LLM 工厂
│   ├── session.py                # COM 线程安全 SessionManager
│   ├── main.py                   # FastAPI 应用 + 全部 REST/WS 端点
│   ├── hfss/
│   │   ├── __init__.py
│   │   ├── com_client.py         # HfssClient 单例
│   │   ├── geometry.py           # 9 个几何操作函数
│   │   ├── simulation.py         # 7 个仿真控制函数
│   │   ├── postprocess.py        # S参数/VSWR/远场提取
│   │   └── array_design.py       # 6 算法阵列权重 + 激励写入
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── system_prompts.py     # 5 个系统提示模板
│   ├── rag/                      # Phase B 桩
│   │   ├── __init__.py
│   │   ├── build_index.py
│   │   └── retriever.py
│   └── parallel/                 # Phase D 桩
│       ├── __init__.py
│       └── scenario_runner.py
│
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py           # LangGraph 意图路由顶层图
│   ├── geometry_agent.py         # 几何 AgentExecutor
│   ├── simulation_agent.py       # 仿真状态机（自动重试收敛）
│   ├── postprocess_agent.py      # 后处理 AgentExecutor
│   ├── array_agent.py            # 阵列设计 AgentExecutor
│   └── tools/
│       ├── __init__.py
│       ├── geometry_tools.py     # 7 个 @tool
│       ├── simulation_tools.py   # 6 个 @tool
│       ├── postprocess_tools.py  # 3 个 @tool
│       └── array_tools.py        # 2 个 @tool
│
├── tests/
│   ├── __init__.py
│   ├── test_hfss/
│   │   ├── __init__.py
│   │   ├── conftest.py           # Mock COM fixture
│   │   ├── test_geometry.py
│   │   └── test_simulation.py
│   └── test_agents/
│       ├── __init__.py
│       └── conftest.py           # Fake LLM fixture
│
├── docs/
│   └── validate_com.py           # COM 连通性验证脚本
│
├── data/
│   └── chromadb/
│       └── .gitkeep
│
└── .venv/                        # Python 3.12.4 虚拟环境（不纳入 Git）
```

---

## 四、已安装依赖版本

| 包 | 版本 |
|----|------|
| fastapi | 0.135.1 |
| uvicorn | 0.41.0 |
| openai | 2.24.0 |
| langchain | 1.2.10 |
| langchain-core | 1.2.17 |
| langchain-openai | 1.1.10 |
| langchain-anthropic | 1.3.4 |
| langgraph | 1.0.10 |
| chromadb | 1.5.2 |
| pydantic | 2.12.5 |
| pydantic-settings | 2.13.1 |
| pywin32 | 311 |
| numpy | 2.4.2 |
| scipy | 1.17.1 |
| plotly | 6.6.0 |
| httpx | 0.28.1 |
| websockets | 16.0 |
| pytest | 9.0.2 |
| python-dotenv | 1.2.2 |

---

## 五、验证结果

### 5.1 Python 环境验证

```
> .venv\Scripts\python.exe -c "import win32com.client; import fastapi; import langgraph; from backend.config import settings; from backend.llm_factory import build_llm; print('All imports OK'); print('Provider:', settings.llm_provider)"

All imports OK
Provider: openai_compatible
```

### 5.2 FastAPI 服务冒烟测试

启动命令：
```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

健康检查响应（`GET /health`）：
```json
{
  "hfss_connected": true,
  "version": "2019.3.0",
  "llm_provider": "openai_compatible",
  "llm_model": "qwen-plus"
}
```

HTTP 状态码：**200 OK** ✅

---

## 六、关键设计决策记录

| 决策 | 方案 | 原因 |
|------|------|------|
| HFSS 接口 | `win32com.client.Dispatch` (COM) | AEDT 19.5 不支持 PyAEDT（需 ≥ 2021 R1） |
| COM 线程安全 | `ThreadPoolExecutor(max_workers=1)` | COM STA 要求操作在同一线程执行 |
| LLM 适配 | `openai_compatible` 覆盖全部国内平台 | OpenAI 兼容接口已成事实标准（Qwen/Kimi/DeepSeek/MiniMax/ZhipuAI 均支持） |
| Pydantic v2 配置 | `model_config = {"extra": "ignore"}` | 避免 `.env` 中 HFSS 路径等字段名与 Settings 字段名不一致导致验证失败 |
| Agent 框架 | LangGraph `StateGraph` | 仿真收敛重试需要有状态循环，LangGraph 原生支持 |
| 仿真重试策略 | `max_delta_s *= 0.5`, `max_passes += 5`，最多 3 次 | 平衡收敛概率与许可证占用时间 |

---

## 七、待解决问题 / 已知限制

| 编号 | 问题 | 状态 | 计划处理阶段 |
|------|------|------|-------------|
| A-1 | `/ws/chat` WebSocket 为桩代码，未接入真实 Agent | ⚠️ 未实现 | Phase C |
| A-2 | RAG 检索器 `is_ready()` 始终为 False（无 PDF 索引） | ⚠️ 桩代码 | Phase B |
| A-3 | `scenario_runner.py` 并行扫描逻辑为 `NotImplementedError` | ⚠️ 桩代码 | Phase D |
| A-4 | HFSS COM 函数中部分细节（如面 ID 获取方式）需结合真实项目调试 | ⚠️ 待验证 | Phase A 收尾 / Phase B |
| A-5 | pywin32 COM 对象注册需管理员权限（测试环境已绕过） | ⚠️ 非阻断 | 部署时处理 |

---

## 八、下一步计划（Phase B）

Phase B 目标：**RAG 知识库 + WebSocket 流式对话接入**

1. 收集 HFSS 2019R3 PDF 手册，放入 `docs/hfss_manuals/`
2. 实现 `backend/rag/build_index.py`：pypdf 解析 → 文本分块 → 嵌入 → ChromaDB 写入
3. 实现 `backend/rag/retriever.py`：向量检索 + 上下文格式化
4. 将 `/ws/chat` WebSocket 接入 `agents/orchestrator.chat()`，实现流式 token 推送
5. 在每个 Agent 的 system prompt 中注入 RAG 检索结果
6. 运行完整测试套件：`.venv\Scripts\pytest tests/ -v`

---

*本文档由 GitHub Copilot 自动生成，记录阶段 A 的完整执行过程与结果。*
