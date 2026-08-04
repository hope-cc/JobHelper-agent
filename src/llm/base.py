"""LLM 客户端抽象基类。"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from .types import Message, StreamEvent


class BaseLLMClient(ABC):
    """统一流式接口，所有适配器必须实现此抽象类。"""

    @abstractmethod
    async def stream(self, messages: list[Message]) -> AsyncIterator[StreamEvent]:
        """发送消息列表，返回异步流式事件迭代器。"""
        ...
        yield  # type: ignore  # pragma: no cover
