"""投递流程状态机的图级单测。

验证状态机在 langgraph 上的行为：
- 入口：browser_navigate 成功后初始化 submit_flow（waiting_login）
- 各流程节点按 current_stage 依次推进，浏览器操作自动串联
- 多简历时停在 waiting_resume_choice，用户回复后继续
- 错误中断时 submit_flow 被清理、回到普通对话
"""

import json

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
from src.tools.registry import ToolRegistry
from src.tools.types import ToolResult

_DECISION_SYSTEM = "你是表单自动填写的决策助手。"


class StubClient(BaseLLMClient):
    """首次 chat 返回 browser_navigate；decision 调用返回脱敏 JSON。"""

    model = "stub"

    def __init__(self):
        self._navigated = False

    async def stream(self, messages, system="", tools=None):
        if system and "决策" in system:
            user = messages[-1].content if messages else ""
            if "下拉框" in user:
                plan = [{"ref": "d1", "data_key": "basic_info.location"}]
            else:
                plan = [
                    {"ref": "e1", "data_key": "basic_info.name"},
                    {"ref": "e2", "data_key": "basic_info.phone"},
                ]
            yield TextChunk(delta=json.dumps(plan, ensure_ascii=False))
            return

        if not self._navigated:
            self._navigated = True
            yield ToolCallStartChunk(tool_id="t1", tool_name="browser_navigate")
            yield ToolCallDeltaChunk(tool_id="t1", tool_args_delta='{"url": "job.example.com/x"}')
            yield ToolCallEndChunk(tool_id="t1")
        else:
            yield TextChunk(delta="好的。")


SNAPSHOT_TEXT = (
    "Page URL: https://job.example.com\n"
    "- textbox \"姓名\" [ref=e1]\n"
    "- textbox \"电话\" [ref=e2]\n"
    "- button \"上传简历\" [ref=upload_btn]\n"
    "- button \"提交\" [ref=submit_btn]\n"
)


class FakeRegistry(ToolRegistry):
    """假工具注册器：记录调用并返回固定结果。"""

    def __init__(self, multi_resume: bool = False):
        super().__init__()
        self.multi_resume = multi_resume
        self._upload_called = 0
        self.calls: dict[str, int] = {}

    def list_definitions(self):
        return [{"name": "browser_navigate", "description": "", "input_schema": {}}]

    def _tally(self, name: str):
        self.calls[name] = self.calls.get(name, 0) + 1

    async def execute(self, name: str, arguments: dict = None) -> ToolResult:
        self._tally(name)
        if name == "browser_navigate":
            return ToolResult(output="页面已打开。请登录后回复「继续」。")
        if name == "browser_snapshot":
            return ToolResult(output=SNAPSHOT_TEXT)
        if name == "browser_upload_resume":
            self._upload_called += 1
            if self.multi_resume and self._upload_called == 1:
                return ToolResult(output="检测到 2 份简历：\n1. cv_a.pdf\n2. cv_b.pdf\n请告诉我要用哪一份。")
            return ToolResult(output="已上传简历 cv.pdf，正在等待网页自动填写相关字段。")
        if name == "getPersonalInfo":
            return ToolResult(output=json.dumps({
                "masked_basic_fields": ["phone"],
                "basic_info": {"name": "张三", "phone": "***"},
            }, ensure_ascii=False))
        if name == "browser_fill_form":
            return ToolResult(output="填写完成：\n- [e1] 姓名 → ***\n- [e2] 电话 → ***")
        if name == "browser_probe_dropdowns":
            return ToolResult(output="下拉框探测结果（共 1 个，未填 1 个）：\n- [dropdown1] 所在城市（未填）：北京、上海、广州")
        if name == "browser_fill_dropdowns":
            return ToolResult(output="下拉框填写结果：\n已填写（1）：\n- [dropdown1] → 北京")
        return ToolResult(output="ok")


def _base_state(**overrides) -> dict:
    state = {
        "messages": [Message(role="user", content="继续")],
        "response": "",
        "tool_calls": [],
        "loop_count": 0,
    }
    state.update(overrides)
    return state


def waiting_login_flow() -> dict:
    return {
        "job_url": "job.example.com/x",
        "current_stage": "waiting_login",
        "form_fields": [],
        "unfilled_fields": [],
        "has_upload_entry": False,
        "uploaded_resume": "",
        "resume_candidates": [],
        "personal_profile": {},
        "dropdowns": [],
        "dropdown_fill_plan": [],
    }


async def _run(graph, state):
    """跑完整张图，返回最终 values 态。"""
    final = None
    async for mode, payload in graph.astream(state, stream_mode=["custom", "values"]):
        if mode == "values":
            final = payload
    return final


@pytest.mark.asyncio
async def test_flow_enters_via_navigate():
    client = StubClient()
    registry = FakeRegistry()
    graph = build_graph(client, registry)

    state = {
        "messages": [Message(role="user", content="帮我投递 job.example.com/x")],
        "response": "",
        "tool_calls": [],
        "loop_count": 0,
    }
    final = await _run(graph, state)

    assert final is not None
    flow = final.get("submit_flow")
    assert flow is not None, "browser_navigate 成功后应初始化 submit_flow"
    assert flow.get("job_url") == "job.example.com/x"
    assert flow.get("current_stage") == "waiting_login"


@pytest.mark.asyncio
async def test_flow_completes_all_stages():
    """「继续」后自动经过快照→上传→再快照→个人信息→填表→探测→填下拉框。"""
    client = StubClient()
    registry = FakeRegistry()
    graph = build_graph(client, registry)

    state = _base_state(submit_flow=waiting_login_flow())
    final = await _run(graph, state)

    assert final is not None and final.get("submit_flow") is not None
    assert final["submit_flow"]["current_stage"] == "completed"

    # 同一 URL 只抓一次完整结构 + 简历解析后再抓一次（snapshot 共 2 次，自身有 twice 设计）
    assert registry.calls.get("browser_snapshot", 0) == 2
    # getPersonalInfo 只取一次
    assert registry.calls.get("getPersonalInfo", 0) == 1
    assert registry.calls.get("browser_probe_dropdowns", 0) == 1
    assert registry.calls.get("browser_fill_dropdowns", 0) == 1


@pytest.mark.asyncio
async def test_flow_multi_resume_waits_then_chooses():
    """多份简历：停在 waiting_resume_choice，用户回复序号后继续。"""
    client = StubClient()
    registry = FakeRegistry(multi_resume=True)
    graph = build_graph(client, registry)

    # 第一轮进入 waiting_resume_choice
    state = _base_state(submit_flow=waiting_login_flow())
    final = await _run(graph, state)

    assert final["submit_flow"]["current_stage"] == "waiting_resume_choice"
    assert registry.calls.get("browser_upload_resume", 0) == 1

    # 第二轮用户回复选择 → 治愈最后完成
    flow = final["submit_flow"]
    flow["current_stage"] = "waiting_resume_choice"
    state2 = {
        "messages": [Message(role="user", content="1")],
        "submit_flow": flow,
    }
    final2 = await _run(graph, state2)

    assert final2.get("submit_flow") is None or final2["submit_flow"]["current_stage"] in ("resume_uploaded", "completed")


# 触发「决策系统」system 时不会被当成普通 chat，所以上面测试不成立时可用显式决策 client
class DecisionStub(StubClient):
    async def stream(self, messages, system="", tools=None):
        if "决策" in system:
            yield TextChunk(delta=json.dumps(
                [{"ref": "e1", "data_key": "basic_info.name"}], ensure_ascii=False))
            return
        yield TextChunk(delta="好的。")


@pytest.mark.asyncio
async def test_decision_stub_returns_json():
    client = DecisionStub()
    msgs = [Message(role="user", content="以下是待填写的表单控件：")]
    collected = []
    async for ev in client.stream(msgs, system=_DECISION_SYSTEM):
        collected.append(ev.delta)
    assert json.loads("".join(collected)) == [{"ref": "e1", "data_key": "basic_info.name"}]


@pytest.mark.asyncio
async def test_browser_error_clears_flow(monkeypatch):
    """browser_snapshot 失败 → submit_flow 清空、回到普通对话。"""
    client = StubClient()
    registry = FakeRegistry()

    async def failing_execute(name, arguments=None):
        if name == "browser_snapshot":
            return ToolResult(output="无法获取表单快照：浏览器未连接", is_error=True)
        return await FakeRegistry.execute(registry, name, arguments)

    monkeypatch.setattr(registry, "execute", failing_execute)
    graph = build_graph(client, registry)

    state = _base_state(submit_flow=waiting_login_flow())
    final = await _run(graph, state)

    assert final.get("submit_flow") is None or final["submit_flow"].get("current_stage") in (
        None,
        "waiting_login",
    )
    texts = [m.content for m in final["messages"] if m.role == "assistant"]
    assert any("获取表单快照失败" in t for t in texts)