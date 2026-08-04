"""共享数据类型定义。"""

from dataclasses import dataclass
from typing import Literal


# ============================================================
# 流式事件类型 —— 每种事件对应一个独立数据类型
# ============================================================

@dataclass
class TextChunk:
    """文本增量。"""
    delta: str


@dataclass
class ThinkingChunk:
    """思考过程增量。"""
    delta: str


@dataclass
class ToolCallStartChunk:
    """工具调用开始。"""
    tool_id: str
    tool_name: str


@dataclass
class ToolCallDeltaChunk:
    """工具参数 JSON 增量。"""
    tool_id: str
    tool_args_delta: str


@dataclass
class ToolCallEndChunk:
    """工具调用结束。"""
    tool_id: str


# 联合类型
StreamEvent = (
    TextChunk
    | ThinkingChunk
    | ToolCallStartChunk
    | ToolCallDeltaChunk
    | ToolCallEndChunk
)


# ============================================================
# 消息 & 配置
# ============================================================

@dataclass
class Message:
    """统一消息格式。"""

    role: Literal["user", "assistant"]
    content: str


@dataclass
class ProviderConfig:
    """LLM 供应商配置。"""

    name: str
    protocol: Literal["anthropic", "openai"]
    model: str
    base_url: str
    api_key: str
    thinking: bool = False
