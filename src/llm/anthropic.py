"""Anthropic 协议适配器。

封装 anthropic SDK 的异步流式 API，将 SDK 事件流转换为统一的 StreamEvent。
采用 event.type 字符串分发，兼容 Anthropic 原生 API 及第三方兼容端点（如 DeepSeek）。
"""

from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from .base import BaseLLMClient
from .types import (
    Message,
    ProviderConfig,
    StreamEvent,
    TextChunk,
    ThinkingChunk,
    ToolCallStartChunk,
    ToolCallDeltaChunk,
    ToolCallEndChunk,
)

# Anthropic thinking 默认 budget tokens
THINKING_BUDGET_TOKENS = 4096


class AnthropicAdapter(BaseLLMClient):
    """Anthropic 协议适配器。"""

    def __init__(self, config: ProviderConfig):
        self.client = AsyncAnthropic(
            base_url=config.base_url,
            api_key=config.api_key,
        )
        self.model = config.model
        self.thinking = config.thinking
        self._current_tool_id: str | None = None

    async def stream(
        self,
        messages: list[Message],
        system: str = "",
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """发送消息，返回统一 StreamEvent 异步迭代器。"""
        api_messages = [_to_anthropic_message(m) for m in messages]

        stream_kwargs: dict = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": 4096,
        }

        if system:
            stream_kwargs["system"] = [{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }]

        if self.thinking:
            stream_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": THINKING_BUDGET_TOKENS,
            }

        if tools:
            # 直接透传：list_definitions() 的格式与 Anthropic tools 参数一致
            stream_kwargs["tools"] = tools

        async with self.client.messages.stream(**stream_kwargs) as stream:
            async for event in stream:
                for chunk in self._map_event(event):
                    yield chunk

    def _map_event(self, event: object) -> list[StreamEvent]:
        """将单个 SDK 事件映射为 StreamEvent 列表。

        纯 event.type 字符串分发，不依赖 isinstance 便捷类型，
        避免不同 SDK 版本或兼容 API 下出现重复/遗漏。
        """
        event_type = getattr(event, "type", None)
        if event_type is None:
            return []

        # --- ContentBlockStartEvent ---
        if event_type == "content_block_start":
            block = getattr(event, "content_block", None)
            if block is not None:
                block_type = getattr(block, "type", None)
                if block_type == "tool_use":
                    self._current_tool_id = getattr(block, "id", "")
                    return [
                        ToolCallStartChunk(
                            tool_id=self._current_tool_id,
                            tool_name=getattr(block, "name", ""),
                        )
                    ]
            return []

        # --- ContentBlockDeltaEvent ---
        if event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta is None:
                return []

            delta_type = getattr(delta, "type", None)

            if delta_type == "text_delta":
                return [TextChunk(delta=getattr(delta, "text", ""))]

            if delta_type == "thinking_delta":
                return [ThinkingChunk(delta=getattr(delta, "thinking", ""))]

            if delta_type == "input_json_delta":
                return [
                    ToolCallDeltaChunk(
                        tool_args_delta=getattr(delta, "partial_json", ""),
                        tool_id=self._current_tool_id or "",
                    )
                ]

            return []

        # --- ContentBlockStopEvent ---
        if event_type == "content_block_stop":
            tid = self._current_tool_id or ""
            self._current_tool_id = None
            return [ToolCallEndChunk(tool_id=tid)]

        # --- MessageStopEvent ---
        if event_type == "message_stop":
            return []

        return []


# ---- 内部辅助 ----

def _to_anthropic_message(m: Message) -> dict:
    """将统一 Message 转为 Anthropic API 格式。

    处理三种情况：
    - tool 角色 → user 消息含 tool_result block
    - assistant 含 tool_calls → content 数组含 text + tool_use blocks
    - 普通消息 → 直接透传
    """
    # tool 结果 → user 消息包裹 tool_result
    if m.role == "tool":
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id or "",
                    "content": m.content,
                }
            ],
        }

    # assistant 工具调用历史 → text + tool_use blocks
    if m.role == "assistant" and m.tool_calls:
        blocks: list[dict] = [{"type": "text", "text": m.content}]
        for tc in m.tool_calls:
            blocks.append({
                "type": "tool_use",
                "id": tc.tool_id,
                "name": tc.tool_name,
                "input": tc.arguments,
            })
        return {"role": "assistant", "content": blocks}

    # 普通 user / assistant 消息
    return {"role": m.role, "content": m.content}
