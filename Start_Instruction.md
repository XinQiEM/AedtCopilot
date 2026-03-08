# AedtCopilot 启动说明

## 前提条件

启动服务前，必须先**手动打开 HFSS** 并确保有活动项目处于打开状态。  
后端通过 Windows COM 接口连接到已运行的 HFSS 实例，不会自动启动软件。

---

## 启动步骤

### 第一步：启动后端（FastAPI，端口 8000）

打开 PowerShell，执行：

```powershell
$env:PYTHONPATH = "D:\Xin\GitCopilot\AedtCopilot"
Start-Process -NoNewWindow -FilePath "D:\Xin\GitCopilot\AedtCopilot\.venv\Scripts\python.exe" `
    -ArgumentList "-m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-access-log"
```

后端启动时会自动完成：
- HFSS COM 会话连接（`SessionManager.initialize()`）
- RAG 向量库加载（`ChromaDB + BAAI/bge-small-en-v1.5`，约需 3–5 秒）

### 第二步：启动前端（Next.js，端口 3000）

```powershell
Start-Process -NoNewWindow -FilePath "cmd.exe" `
    -ArgumentList "/c cd /d D:\Xin\GitCopilot\AedtCopilot\frontend && npm run dev"
```

### 第三步：验证服务状态

等待约 10 秒后，执行健康检查：

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing | Select-Object -ExpandProperty Content
```

正常返回示例：
```json
{
  "hfss_connected": true,
  "version": "2019.3.0",
  "llm_provider": "openai_compatible",
  "llm_model": "Qwen/Qwen3-32B",
  "rag_ready": true,
  "rag_chunks": 3579
}
```

### 第四步：打开界面

浏览器访问：**http://localhost:3000**

---

## 常见问题

### 端口已被占用（`[Errno 10048]`）

说明上次启动的进程仍在运行，无需重新启动。直接访问 http://localhost:3000 即可。

若确需重启，先终止占用端口的进程：

```powershell
# 查找占用端口的 PID
netstat -ano | findstr "LISTENING" | findstr ":8000\|:3000"

# 根据 PID 终止进程（将 <PID> 替换为实际值）
Stop-Process -Id <PID> -Force
```

### HFSS 未连接（`hfss_connected: false`）

- 确认 HFSS 已打开且有活动项目
- 重启后端服务

### RAG 未就绪（`rag_ready: false`）

向量库尚未构建，执行以下命令建立索引（需要 HFSS 帮助文档 PDF）：

```powershell
$env:PYTHONPATH = "D:\Xin\GitCopilot\AedtCopilot"
.\.venv\Scripts\python.exe -m backend.rag.build_index `
    --pdfs "D:\Program Files\AnsysEM\AnsysEM19.5\Win64\Help\HFSS\HFSSScriptingGuide.pdf"
```

系统在无 RAG 时仍可正常运行（降级为纯 LLM 模式）。

---

## 服务地址速查

| 服务 | 地址 |
|------|------|
| 前端 UI | http://localhost:3000 |
| 后端 API | http://127.0.0.1:8000 |
| 后端 API 文档 | http://127.0.0.1:8000/docs |
| 健康检查 | http://127.0.0.1:8000/health |
| 切换 LLM | `POST http://127.0.0.1:8000/llm/config` |

---

## 当前环境配置

| 项目 | 值 |
|------|----|
| Python 虚拟环境 | `D:\Xin\GitCopilot\AedtCopilot\.venv` |
| 前端目录 | `D:\Xin\GitCopilot\AedtCopilot\frontend` |
| HFSS 版本 | 19.5 (AEDT 2019 R3) |
| LLM Provider | openai_compatible（Qwen3-32B） |
| Embedding 模型 | BAAI/bge-small-en-v1.5（本地） |
