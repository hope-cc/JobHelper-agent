"""LLM 客户端工厂函数。"""

from .anthropic import AnthropicAdapter
from .base import BaseLLMClient
from .openai import OpenAIAdapter
from .types import ProviderConfig


def create_client(config: ProviderConfig) -> BaseLLMClient:
    """根据 ProviderConfig.protocol 创建对应的适配器实例。"""
    if config.protocol == "anthropic":
        return AnthropicAdapter(config)
    elif config.protocol == "openai":
        return OpenAIAdapter(config)
    else:
        raise ValueError(f"不支持的协议类型: '{config.protocol}'")
