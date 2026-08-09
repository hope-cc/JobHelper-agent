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


@dataclass
class ToolResultEvent:
    """工具执行结果事件。由 tool_node 在工具执行后产出。"""

    tool_id: str
    """对应 ToolCallStartChunk 的 tool_id。"""

    content: str
    """工具执行返回的文本，或错误信息。"""

    is_error: bool = False
    """是否为错误结果。前端据此决定展示样式。"""


# 联合类型
StreamEvent = (
    TextChunk
    | ThinkingChunk
    | ToolCallStartChunk
    | ToolCallDeltaChunk
    | ToolCallEndChunk
    | ToolResultEvent
)


# ============================================================
# 消息 & 配置
# ============================================================

@dataclass
class ToolCall:
    """一次完整的工具调用，由 LLM 产出的 JSON 参数字符串解析而来。"""

    tool_id: str
    """LLM 返回的唯一标识符。"""

    tool_name: str
    """工具名称，对应注册中心中的 name。"""

    arguments: dict
    """解析后的 JSON 参数字典。解析失败时为空字典 {}。"""


@dataclass
class Message:
    """统一消息格式。"""

    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] | None = None
    """assistant 消息可能包含的工具调用列表。无工具调用时为 None。"""

    tool_call_id: str | None = None
    """tool 角色消息关联的 tool_call 唯一标识。非 tool 消息时为 None。"""


@dataclass
class ProviderConfig:
    """LLM 供应商配置。"""

    name: str
    protocol: Literal["anthropic", "openai"]
    model: str
    base_url: str
    api_key: str
    thinking: bool = False
