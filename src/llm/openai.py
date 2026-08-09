"""OpenAI 协议适配器。

封装 openai SDK 的异步流式 API，将 SSE chunk 流转换为统一的 StreamEvent。
"""

import json
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from .base import BaseLLMClient
from .types import (
    Message,
    ProviderConfig,
    StreamEvent,
    TextChunk,
    ToolCallStartChunk,
    ToolCallDeltaChunk,
    ToolCallEndChunk,
)


class OpenAIAdapter(BaseLLMClient):
    """OpenAI 协议适配器。"""

    def __init__(self, config: ProviderConfig):
        self.client = AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )
        self.model = config.model

    async def stream(
        self,
        messages: list[Message],
        system: str = "",
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """发送消息，返回统一 StreamEvent 异步迭代器。"""
        api_messages = [_to_openai_message(m) for m in messages]

        create_kwargs: dict = {
            "model": self.model,
            "messages": api_messages,
            "stream": True,
        }

        if system:
            create_kwargs["instructions"] = system

        if tools:
            create_kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ]

        response = await self.client.chat.completions.create(**create_kwargs)

        # 追踪 tool_call 生命周期
        seen_tool_calls: dict[int, dict] = {}
        # 追踪已产出文本长度，防止兼容 API 返回累积内容或重复
        _text_emitted = 0

        async for chunk in response:
            for event in self._map_chunk(chunk, seen_tool_calls, _text_emitted):
                if isinstance(event, TextChunk):
                    _text_emitted += len(event.delta)
                yield event

    def _map_chunk(
        self, chunk, seen: dict[int, dict], text_emitted: int = 0
    ) -> list[StreamEvent]:
        """将单个 OpenAI ChatCompletionChunk 映射为 StreamEvent 列表。

        text_emitted 用于去重：若 API 返回累积文本而非纯增量，
        仅产出自上次以来的新增部分。
        """
        results: list[StreamEvent] = []

        if not chunk.choices:
            return results

        choice = chunk.choices[0]
        delta = choice.delta

        # --- 文本增量（含去重） ---
        if delta.content:
            if len(delta.content) > text_emitted:
                new_text = delta.content[text_emitted:]
                if new_text:
                    results.append(TextChunk(delta=new_text))

        # --- 工具调用增量 ---
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index

                if idx not in seen:
                    seen[idx] = {
                        "id": tc.id or "",
                        "name": tc.function.name if tc.function else "",
                        "done": False,
                    }
                    results.append(
                        ToolCallStartChunk(
                            tool_id=tc.id or "",
                            tool_name=(
                                tc.function.name if tc.function else ""
                            ),
                        )
                    )

                entry = seen[idx]
                if (
                    tc.function
                    and tc.function.arguments
                    and not entry["done"]
                ):
                    results.append(
                        ToolCallDeltaChunk(
                            tool_id=entry["id"],
                            tool_args_delta=tc.function.arguments,
                        )
                    )

        # --- 工具调用结束 ---
        if choice.finish_reason == "tool_calls":
            for entry in seen.values():
                if not entry["done"]:
                    entry["done"] = True
                    results.append(
                        ToolCallEndChunk(tool_id=entry["id"])
                    )

        return results


# ---- 内部辅助 ----

def _to_openai_message(m: Message) -> dict:
    """将统一 Message 转为 OpenAI API 格式。

    处理三种情况：
    - tool 角色 → 附加 tool_call_id
    - assistant 含 tool_calls → 附加 tool_calls 数组
    - 普通消息 → 直接透传
    """
    if m.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": m.tool_call_id or "",
            "content": m.content,
        }

    if m.role == "assistant" and m.tool_calls:
        return {
            "role": "assistant",
            "content": m.content,
            "tool_calls": [
                {
                    "id": tc.tool_id,
                    "type": "function",
                    "function": {
                        "name": tc.tool_name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in m.tool_calls
            ],
        }

    return {"role": m.role, "content": m.content}
