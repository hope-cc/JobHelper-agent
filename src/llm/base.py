"""LLM 客户端抽象基类。"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from .types import Message, StreamEvent


class BaseLLMClient(ABC):
    """统一流式接口，所有适配器必须实现此抽象类。"""

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        system: str = "",
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """发送消息列表，返回异步流式事件迭代器。

        Args:
            messages: 对话历史，可能包含 user / assistant / tool 角色
            system: 可选的 system prompt 文本
            tools: 可选的工具定义列表，每个元素格式为：
                {"name": str, "description": str, "input_schema": dict}
                若为 None 或不传，则 LLM 不会调用任何工具。

        Returns:
            StreamEvent 异步迭代器，包含文本、思考过程和工具调用事件。
        """
        ...
        yield  # type: ignore  # pragma: no cover
