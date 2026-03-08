# 阶段 C 执行结果报告

**项目**：AedtCopilot — 本地 HFSS 智能助手  
**阶段**：C — 前端 Web 应用层  
**日期**：2026-03-03  
**状态**：✅ 全部完成，前后端联调通过

---

## 1. 阶段目标

| 目标 | 说明 |
|------|------|
| 前端项目初始化 | Next.js 16 + TypeScript + Tailwind + shadcn/ui |
| 双栏交互界面 | 左（聊天面板 40%）+ 右（结果面板 60%）全屏布局 |
| WebSocket 流式对话 | 实时推送 intent / rag / token / done / error 事件 |
| 结果可视化 | Plotly：S 参数、Smith 圆图、远场方向图 Tabs |
| LLM 热配置 | Drawer 界面支持 13 个平台预设，保存后无需重启 |
| 状态栏 | 顶部实时显示 HFSS 连接状态、LLM 模型、RAG 就绪情况 |
| API 代理 | Next.js route handler 代理后端 `/health`、`/llm/*` |

---

## 2. 环境与依赖

### 2.1 运行环境

```
Node.js   v24.13.0
npm       11.6.2
Next.js   16.1.6 (create-next-app)
```

### 2.2 新增前端依赖

**生产依赖**

| 包 | 用途 |
|----|------|
| react-plotly.js | Plotly React 封装 |
| plotly.js | 交互式图表引擎 |
| lucide-react | 图标库（Wifi / Settings / Trash2 等） |
| react-syntax-highlighter | 消息气泡中的代码块高亮 |

**类型声明**

| 包 | 用途 |
|----|------|
| @types/react-plotly.js | Plotly 类型定义 |
| @types/react-syntax-highlighter | 高亮器类型定义 |

**shadcn/ui 组件**（通过 `npx shadcn@latest add` 添加）

```
button  input  select  drawer  tabs  badge  scroll-area  separator  textarea
```

安装命令：

```powershell
cd frontend
npm install react-plotly.js plotly.js lucide-react react-syntax-highlighter `
    @types/react-syntax-highlighter @types/react-plotly.js
npx --yes shadcn@latest add button input select drawer tabs badge scroll-area separator textarea
```

---

## 3. 文件结构

### 3.1 新增文件

```
frontend/
├── .env.local                                   # NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000
├── src/
│   ├── lib/
│   │   └── types.ts                             # 全局 TypeScript 类型定义
│   ├── hooks/
│   │   ├── useChat.ts                           # WebSocket 流式对话 Hook
│   │   └── useHfssStatus.ts                     # 后端健康状态轮询 Hook
│   ├── components/
│   │   ├── HfssStatusBar.tsx                    # 顶部状态栏
│   │   ├── ChatPanel.tsx                        # 左侧聊天面板
│   │   ├── ResultPanel.tsx                      # 右侧结果面板（Plotly 图表）
│   │   └── LLMSettingsDrawer.tsx                # LLM 配置侧边抽屉
│   └── app/
│       ├── page.tsx                             # 主页（双栏布局，覆盖原始占位页）
│       ├── layout.tsx                           # 全局布局（dark 模式、语言 zh-CN）
│       └── api/
│           ├── health/route.ts                  # GET /api/health → 后端 /health
│           └── llm/[...path]/route.ts           # GET|POST /api/llm/* → 后端 /llm/*
```

### 3.2 修改文件（后端）

| 文件 | 变更内容 |
|------|---------|
| `backend/main.py` | 新增 `POST /llm/config`（热切换 LLM 配置）和 `POST /llm/test`（连通性测试） |

---

## 4. 核心实现说明

### 4.1 `src/lib/types.ts` — 全局类型

定义了以下接口：

| 类型 | 说明 |
|------|------|
| `ChatMessage` | 聊天消息（含 intent/ragHint/streaming 字段） |
| `StreamEvent` | WebSocket 事件（type: intent/rag/token/done/error） |
| `HealthStatus` | 后端健康检查响应 |
| `LLMConfig` | LLM 配置（兼容所有 4 种 provider） |
| `SParamData` | S 参数图表数据（freq_ghz + traces 字典） |
| `FarFieldData` | 远场方向图数据（theta_deg + gain_dbi） |

### 4.2 `useChat.ts` — WebSocket Hook

**功能**：
- 连接 `ws://127.0.0.1:8000/ws/chat`，断线后 3 秒自动重连
- 消息发送：附带完整历史（过滤系统消息和流式未完成消息）
- 流式渲染：`token` 事件逐字追加到 `content`，`streaming=true` 时显示光标动画
- 状态暴露：`connected`、`sending`、`messages`、`sendMessage`、`clearMessages`

**事件处理**：

| 事件类型 | 处理 |
|---------|------|
| `intent` | patchMessage → `msg.intent = "geometry"` 等 |
| `rag` | patchMessage → `msg.ragHint = "..."` |
| `token` | appendChunk → `msg.content += token` |
| `done` | patchMessage → `streaming = false`；释放 sending 锁 |
| `error` | patchMessage → 替换内容为 `⚠️ ...`；释放 sending 锁 |

### 4.3 `ChatPanel.tsx` — 聊天面板

- `MessageBubble`：区分 user（右对齐，主色调）/ assistant（左对齐，灰底）
- 代码块检测：正则解析 ` ```lang\n...\n``` ` → `SyntaxHighlighter`（atomOneDark 主题）
- Intent 徽章：按意图分色（geometry 蓝 / simulation 橙 / postprocess 紫 / array 绿）
- RAG 徽章：📚 显示命中文档提示
- 流式光标：`streaming=true` 时末尾显示闪烁竖线
- `Enter` 发送，`Shift+Enter` 换行；`disabled` 当 sending 或 disconnected

### 4.4 `ResultPanel.tsx` — 结果面板

**三个 Tab**：

| Tab | 图表类型 | 空状态 |
|-----|---------|--------|
| S 参数 | Plotly Rectangular（频率 vs dB） | 占位符提示 |
| Smith 圆图 | 占位符（待仿真数据） | — |
| 方向图 | Plotly Polar（theta vs GainTotal） | 占位符提示 |

- Plotly 通过 `dynamic(import(...), { ssr: false })` 延迟加载（客户端渲染）
- 深色主题：`paper_bgcolor/plot_bgcolor = "transparent"`，字体颜色 `#e4e4e7`
- `SimProgressBar`：Pass N/M + ΔS 进度条（预留接口，待后端推送仿真状态）

### 4.5 `LLMSettingsDrawer.tsx` — LLM 配置

**支持 13 个平台预设**：

| 分类 | 平台 |
|------|------|
| 国际 | OpenAI、Azure OpenAI、Anthropic Claude |
| 国内（自动填 base_url）| 魔塔 ModelScope、通义千问 DashScope、Kimi、MiniMax、DeepSeek、智谱 AI、百度千帆 |
| 本地 | Ollama/LM Studio、自定义 OpenAI 兼容接口 |

**核心逻辑**：
- 选中国内或本地平台 → 自动填入 `base_url` 和默认模型名，后端统一映射为 `openai_compatible`
- Azure OpenAI → 条件展示 Endpoint / Deployment / API Version 三个额外字段
- 测试连接：调用 `POST /api/llm/test`，显示延迟（ms）或错误信息
- 保存并热切换：调用 `POST /api/llm/config`，后端重置 LLM 缓存，无需重启服务

### 4.6 `HfssStatusBar.tsx` — 顶部状态栏

- 每 5 秒轮询 `GET /api/health`，实时更新状态徽章
- HFSS 连接状态：绿色 `Cpu` 图标 + 版本号 / 红色 "HFSS 未连接"
- LLM 模型：蓝色徽章显示当前 `llm_model`
- RAG 状态：teal "RAG N块" / 灰色 "RAG 未就绪"
- 右侧：`LLMSettingsDrawer` 入口按钮

### 4.7 后端 `/llm/config` & `/llm/test`

```
POST /llm/config   → 热更新 settings 字段 + invalidate_llm_cache()
POST /llm/test     → 临时替换配置 → llm.invoke("Hi") → 测量耗时 → 自动回滚
```

---

## 5. 测试结果

| 测试项 | 命令/操作 | 结果 |
|--------|---------|------|
| TypeScript 类型检查 | `npx tsc --noEmit` | ✅ 0 错误 |
| 前端服务启动 | `npm run dev` → `:3000` | ✅ 200 OK |
| 健康代理 | `GET /api/health` | ✅ 返回后端真实数据 |
| LLM 配置接口 | `POST /llm/config {...}` | ✅ `{"ok":true}` |
| 浏览器预览 | 打开 `http://127.0.0.1:3000` | ✅ 双栏界面渲染正常 |

---

## 6. 待后续完善

| 事项 | 说明 |
|------|------|
| ResultPanel 数据接入 | 待后端推送 S 参数/方向图数据时接入（预留 useState 接口） |
| 仿真进度推送 | `SimProgressBar` 组件已就绪，需后端 SSE 或 WebSocket 推送 `pass/deltaS` |
| 对话历史持久化 | 使用 `localStorage` 保存 messages（可在 useChat 中扩展） |
| RAG 索引后前端感知 | `/rag/rebuild` 完成后通知前端刷新状态栏 |
| 错误边界 | 为 Plotly 动态加载添加 ErrorBoundary |

---

## 7. 启动方式

```powershell
# 后端（项目根目录）
cd D:\Xin\GitCopilot\AedtCopilot
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# 前端（frontend/ 目录）
cd D:\Xin\GitCopilot\AedtCopilot\frontend
npm run dev

# 浏览器访问
http://127.0.0.1:3000
```

---

## 8. 阶段进度总览

| 阶段 | 内容 | 状态 |
|------|------|------|
| A | 基础框架（venv / COM / FastAPI / LangGraph 骨架） | ✅ 完成 |
| B | RAG 知识库 + 流式对话后端 | ✅ 代码完成（索引待 API Key） |
| C | 前端 Web 应用层 | ✅ 完成 |
| D | HFSS COM 工具层深化（geometry/simulation/postprocess 完整实现） | 🔲 下一阶段 |
| E | 端到端集成测试与优化 | 🔲 待办 |
| F | 增强功能（并行仿真、近场可视化等） | 🔲 待办 |

---

*本文档由 GitHub Copilot 自动生成，记录 AedtCopilot 阶段 C 执行过程与结果。*
