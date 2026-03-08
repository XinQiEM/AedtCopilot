from __future__ import annotations
from langchain_core.language_models import BaseChatModel
from backend.config import Settings

_llm_cache: BaseChatModel | None = None


def build_llm(cfg: Settings | None = None, reload: bool = False) -> BaseChatModel:
    """
    根据 cfg（默认使用全局 settings）构建并缓存 LangChain 聊天模型。
    reload=True 时强制重建（用于运行时通过 REST API 切换配置）。

    支持 Provider：
      openai            - OpenAI 官方
      azure_openai      - Azure OpenAI
      anthropic         - Anthropic Claude
      openai_compatible - 所有 OpenAI 兼容接口：
                          魔塔社区 / 通义千问 DashScope / Kimi / MiniMax /
                          DeepSeek / 智谱 AI / 百度千帆 / 本地 Ollama 等
    """
    global _llm_cache
    if _llm_cache is not None and not reload:
        return _llm_cache

    from backend.config import settings
    c = cfg or settings

    if c.llm_provider == "openai":
        from langchain_openai import ChatOpenAI
        _llm_cache = ChatOpenAI(
            api_key=c.llm_api_key,
            model=c.llm_model,
            temperature=c.llm_temperature,
            max_tokens=c.llm_max_tokens,
            streaming=c.llm_streaming,
        )

    elif c.llm_provider == "azure_openai":
        from langchain_openai import AzureChatOpenAI
        _llm_cache = AzureChatOpenAI(
            api_key=c.llm_api_key,
            azure_endpoint=c.azure_endpoint,
            azure_deployment=c.azure_deployment or c.llm_model,
            api_version=c.azure_api_version,
            temperature=c.llm_temperature,
            max_tokens=c.llm_max_tokens,
            streaming=c.llm_streaming,
        )

    elif c.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        _llm_cache = ChatAnthropic(  # type: ignore[call-arg]
            api_key=c.llm_api_key,
            model=c.llm_model,
            temperature=c.llm_temperature,
            max_tokens=c.llm_max_tokens,
            streaming=c.llm_streaming,
        )

    elif c.llm_provider == "openai_compatible":
        # 覆盖范围：本地 Ollama/LM Studio、魔塔社区、通义千问 DashScope、
        # Kimi Moonshot、MiniMax、DeepSeek、智谱 AI、百度千帆等
        # 所有实现了 OpenAI Chat Completions 兼容协议的服务均可通过此分支接入。
        from langchain_openai import ChatOpenAI

        # Qwen3 系列模型通过 model_name 前缀检测：
        #   - 非 streaming 调用要求 enable_thinking=false 作为 extra_body 参数
        #   - streaming 调用同样需要，通过 extra_body 传入
        model_lower = c.llm_model.lower()
        if "qwen3" in model_lower:
            # LangChain ChatOpenAI 支持将 extra_body 合并到每次请求的 request_options
            _llm_cache = ChatOpenAI(
                api_key=c.llm_api_key or "not-needed",
                base_url=c.llm_base_url,
                model=c.llm_model,
                temperature=c.llm_temperature,
                max_tokens=c.llm_max_tokens,
                streaming=c.llm_streaming,
                extra_body={"enable_thinking": False},
            )
        elif "kimi-k2.5" in model_lower:
            # kimi-k2.5: temperature / top_p / n 不可修改，不向 API 传入该参数
            _llm_cache = ChatOpenAI(
                api_key=c.llm_api_key or "not-needed",
                base_url=c.llm_base_url,
                model=c.llm_model,
                max_tokens=c.llm_max_tokens,
                streaming=c.llm_streaming,
            )
        else:
            _llm_cache = ChatOpenAI(
                api_key=c.llm_api_key or "not-needed",
                base_url=c.llm_base_url,
                model=c.llm_model,
                temperature=c.llm_temperature,
                max_tokens=c.llm_max_tokens,
                streaming=c.llm_streaming,
            )

    else:
        raise ValueError(f"未知 LLM Provider: {c.llm_provider}")

    return _llm_cache


def invalidate_llm_cache() -> None:
    """清除缓存，下次调用 build_llm() 时重建实例。"""
    global _llm_cache
    _llm_cache = None
