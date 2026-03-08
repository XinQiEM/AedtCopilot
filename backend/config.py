from __future__ import annotations
from typing import Literal, Optional
from pydantic_settings import BaseSettings

# 支持的 LLM Provider 枚举
LLMProvider = Literal["openai", "azure_openai", "anthropic", "openai_compatible"]


class Settings(BaseSettings):
    # ===================== LLM 多 Provider 配置 =====================
    # 选择 Provider：openai | azure_openai | anthropic | openai_compatible
    llm_provider: LLMProvider = "openai"

    # 通用字段（所有 Provider 均适用）
    llm_api_key: str = ""               # 对应各 Provider 的 API Key
    llm_model: str = "gpt-4o"           # 模型名称
    llm_base_url: Optional[str] = None  # 自定义 Endpoint URL；openai_compatible 必填
    llm_temperature: float = 0.0        # 生成温度（0=确定性最高）
    llm_max_tokens: int = 4096
    llm_streaming: bool = True          # 是否启用流式输出

    # Azure OpenAI 专用字段（llm_provider="azure_openai" 时生效）
    azure_api_version: str = "2024-02-01"
    azure_deployment: str = ""          # Azure 部署名，不填则使用 llm_model
    azure_endpoint: Optional[str] = None  # https://<resource>.openai.azure.com

    # Anthropic 专用字段（llm_provider="anthropic" 时生效）
    anthropic_api_version: str = "2023-06-01"

    # ===================== HFSS 环境 =====================
    hfss_install_path: str = r"D:\Program Files\AnsysEM\AnsysEM19.5\Win64"
    hfss_executable: str = r"D:\Program Files\AnsysEM\AnsysEM19.5\Win64\ansysedt.exe"
    hfss_com_progid: str = "AnsoftHfss.HfssScriptInterface"
    hfss_project_dir: str = r"D:\Projects\HFSS"

    # ===================== 后端服务 =====================
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # ===================== Embedding（RAG 向量化）=====================
    # Embedding 输出来源: "openai" | "local"
    # "local" 使用 sentence-transformers 本地模型，无需 API Key
    embedding_provider: str = "openai"
    # 嵌入模型名称——openai: text-embedding-v3 / text-embedding-3-small
    #                ——local:  HuggingFace 模型名，如 BAAI/bge-small-en-v1.5
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # 嵌入 API Key —— 默认复用 llm_api_key；如需独立 Key 则单独设置
    embedding_api_key: str = ""
    # 嵌入 Base URL —— 默认复用 llm_base_url
    embedding_base_url: Optional[str] = None
    # 每批嵌入的最大文本数（避免超出 API 限制）
    embedding_batch_size: int = 25

    # ===================== 其他 =====================
    chromadb_path: str = "./data/chromadb"
    debug: bool = False
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
