"""SSE 流式适配器。

将内部 StreamEvent 转换为 Server-Sent Events 格式输出。
"""

import json
from collections.abc import AsyncIterator

from src.llm.types import StreamEvent, TextChunk, ThinkingChunk


def to_sse(event: StreamEvent) -> str:
    """将单个 StreamEvent 转换为 SSE 格式字符串。"""
    if isinstance(event, TextChunk):
        data = json.dumps({"delta": event.delta}, ensure_ascii=False)
        return f"event: text\ndata: {data}\n\n"

    if isinstance(event, ThinkingChunk):
        data = json.dumps({"delta": event.delta}, ensure_ascii=False)
        return f"event: thinking\ndata: {data}\n\n"

    # ToolCall* 等事件暂不处理
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
