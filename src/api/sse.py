"""SSE 流式适配器。

将内部 StreamEvent 转换为 Server-Sent Events 格式输出。
"""

import json
from collections.abc import AsyncIterator

from src.llm.types import (
    StreamEvent,
    TextChunk,
    ThinkingChunk,
    ToolCallStartChunk,
    ToolCallDeltaChunk,
    ToolCallEndChunk,
    ToolResultEvent,
)


def to_sse(event: StreamEvent) -> str:
    """将单个 StreamEvent 转换为 SSE 格式字符串。

    映射关系：
        TextChunk           → event: text
        ThinkingChunk       → event: thinking
        ToolCallStartChunk  → event: tool_start
        ToolCallDeltaChunk  → event: tool_delta
        ToolCallEndChunk    → event: tool_end
        ToolResultEvent     → event: tool_result
    """
    if isinstance(event, TextChunk):
        data = json.dumps({"delta": event.delta}, ensure_ascii=False)
        return f"event: text\ndata: {data}\n\n"

    if isinstance(event, ThinkingChunk):
        data = json.dumps({"delta": event.delta}, ensure_ascii=False)
        return f"event: thinking\ndata: {data}\n\n"

    if isinstance(event, ToolCallStartChunk):
        data = json.dumps(
            {"tool_id": event.tool_id, "tool_name": event.tool_name},
            ensure_ascii=False,
        )
        return f"event: tool_start\ndata: {data}\n\n"

    if isinstance(event, ToolCallDeltaChunk):
        data = json.dumps(
            {"tool_id": event.tool_id, "delta": event.tool_args_delta},
            ensure_ascii=False,
        )
        return f"event: tool_delta\ndata: {data}\n\n"

    if isinstance(event, ToolCallEndChunk):
        data = json.dumps({"tool_id": event.tool_id}, ensure_ascii=False)
        return f"event: tool_end\ndata: {data}\n\n"

    if isinstance(event, ToolResultEvent):
        data = json.dumps(
            {
                "tool_id": event.tool_id,
                "content": event.content,
                "is_error": event.is_error,
            },
            ensure_ascii=False,
        )
        return f"event: tool_result\ndata: {data}\n\n"

    return ""


async def sse_stream(stream: AsyncIterator[StreamEvent]) -> AsyncIterator[str]:
    """将 StreamEvent 异步迭代器转换为 SSE 字符串异步生成器。

    流结束后自动发送 done 事件。
    """
    async for event in stream:
        sse_msg = to_sse(event)
        if sse_msg:
            yield sse_msg

    yield "event: done\ndata: {}\n\n"
