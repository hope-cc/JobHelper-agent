"""投递流程「下一步提醒」注入的图级单测。

验证：进入投递流程后，工具执行完会在当前图运行的消息历史里注入一条
<system-reminder>，并（有 conversation_id 时）持久化到会话存储。
"""

import pytest

from src.chat.graph import build_graph
from src.llm.base import BaseLLMClient
from src.llm.types import (
    Message,
    TextChunk,
    ToolCallDeltaChunk,
    ToolCallEndChunk,
    ToolCallStartChunk,
)
from src.tools import ToolResult
from src.tools.registry import ToolRegistry


class StubClient(BaseLLMClient):
    """第一次调用产出 browser_probe_dropdowns 工具调用，第二次产出纯文本结束。"""

    model = "stub"

    def __init__(self):
        self.calls = 0

    async def stream(self, messages, system="", tools=None):
        self.calls += 1
        if self.calls == 1:
            yield ToolCallStartChunk(tool_id="t1", tool_name="browser_probe_dropdowns")
            yield ToolCallDeltaChunk(tool_id="t1", tool_args_delta='{"refs": []}')
            yield ToolCallEndChunk(tool_id="t1")
        else:
            yield TextChunk(delta="完成")


@pytest.mark.asyncio
async def test_submit_flow_reminder_injected(monkeypatch):
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "src.api.storage.add_system_reminder",
        lambda cid, reminder: recorded.append((cid, reminder)),
    )

    client = StubClient()
    registry = ToolRegistry.get_instance()

    async def fake_execute(name, args):
        return ToolResult(output="ok")

    monkeypatch.setattr(registry, "execute", fake_execute)

    graph = build_graph(client, registry, conversation_id="cid")
    state = {
        "messages": [Message(role="user", content="继续")],
        "response": "",
        "tool_calls": [],
        "loop_count": 0,
    }

    final = None
    async for mode, payload in graph.astream(state, stream_mode=["custom", "values"]):
        if mode == "values":
            final = payload

    # 提醒已持久化到会话存储
    assert len(recorded) == 1
    cid, reminder = recorded[0]
    assert cid == "cid"
    assert "browser_fill_dropdowns" in reminder

    # 提醒已注入当前图运行的消息历史（对下一步 chat_node 可见）
    assert final is not None
    reminders = [m.content for m in final["messages"] if "<system-reminder>" in m.content]
    assert reminders, "应在消息历史中找到 system-reminder"
    assert "browser_fill_dropdowns" in reminders[0]

    # 已进入投递流程标记
    assert final.get("in_submit_flow") is True
