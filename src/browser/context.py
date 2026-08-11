"""会话上下文。

通过 ContextVar 将当前请求的 conversation_id 透传给工具函数。
在 API 层的 event_generator 内设置，随异步上下文一路透传到工具执行处。
"""

from contextvars import ContextVar

_current_conversation: ContextVar[str] = ContextVar(
    "current_conversation", default=""
)


def set_current_conversation(conversation_id: str) -> None:
    """在当前异步上下文中设置会话 ID。"""
    _current_conversation.set(conversation_id)


def get_current_conversation() -> str:
    """获取当前异步上下文中的会话 ID。未设置时返回空字符串。"""
    return _current_conversation.get()
