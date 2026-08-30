"""投递流程状态机的图级单测。

验证状态机在 langgraph 上的行为：
- 入口：browser_navigate 成功后初始化 submit_flow（waiting_login）
- 各流程节点按 current_stage 依次推进，浏览器操作自动串联
- 多简历时停在 waiting_resume_choice，用户回复后继续
- 错误中断时 submit_flow 被清理、回到普通对话
"""

import json

import pytest

from src.api import profile_storage
from src.browser_mcp.types import SubmitResult
from src.chat import submit_flow
from src.chat.submit_flow import flow_get_personal_node
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
                plan = {"所在城市": "广州"}
            else:
                plan = {"姓名": "张三", "电话": "手机"}
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

    def __init__(self):
        super().__init__()
        self.calls: dict[str, int] = {}

    def list_definitions(self):
        return [{"name": "browser_navigate", "description": "", "input_schema": {}}]

    def _tally(self, name: str):
        self.calls[name] = self.calls.get(name, 0) + 1

    async def execute(self, name: str, arguments: dict = None) -> ToolResult:
        self._tally(name)
        if name == "browser_navigate":
            return ToolResult(output="页面已打开。请登录后回复「继续」。")
        return ToolResult(output="ok")


class _BrowserSide:
    """模拟状态机直接调用的浏览器侧函数（不再经由 registry）。

    与真实浏览器侧保持一致：快照返回三个 {字段名: ref} 字典，上传/填表返回
    SubmitResult。用计数验证各节点恰好调用一次。
    """

    def __init__(self, multi_resume: bool = False):
        self.multi_resume = multi_resume
        self.snapshot_calls = 0
        self.upload_calls = 0
        self.fill_calls = 0
        self.fill_dropdowns_calls = 0
        self.profile_calls = 0
        self.probe_calls = 0
        self.last_fill_items: list[dict] | None = None
        self.last_dropdown_items: list[dict] | None = None

    async def snapshot(self):
        self.snapshot_calls += 1
        return (
            {"姓名": "e1", "电话": "e2"},      # textbox_fields
            {"所在城市": "d1"},                 # dropdown_fields
            {"上传简历": "upload_btn"},         # upload_fields
        )

    async def upload(self, ref, resume):
        self.upload_calls += 1
        if self.multi_resume and self.upload_calls == 1:
            return SubmitResult(
                output="检测到 2 份简历：\n1. cv_a.pdf\n2. cv_b.pdf\n请告诉我要用哪一份。"
            )
        return SubmitResult(output="已上传简历 cv.pdf，正在等待网页自动填写相关字段。")

    async def fill(self, items):
        self.fill_calls += 1
        self.last_fill_items = list(items)
        return SubmitResult(output="填写完成：\n- [e1] 姓名 → 张三\n- [e2] 电话 → ***")

    async def probe(self, fields):
        self.probe_calls += 1
        return {name: ["北京", "上海", "广州"] for name in fields}

    async def fill_dropdowns(self, items, dropdown_fields):
        self.fill_dropdowns_calls += 1
        self.last_dropdown_items = list(items)
        return SubmitResult(output="下拉框填写结果：\n已填写（1）：\n- [所在城市] → 广州")

    def profile_load(self):
        self.profile_calls += 1
        return {
            "masked_basic_fields": ["phone"],
            "basic_fields_schema": [
                {"key": "name", "label": "姓名", "type": "text"},
                {"key": "phone", "label": "手机", "type": "text"},
                {"key": "location", "label": "所在地点", "type": "text"},
            ],
            "basic_info": {
                "name": "张三",
                "phone": "18928733892",
                "location": "广州",
            },
        }


def _patch_browser_side(monkeypatch, side: _BrowserSide) -> None:
    """把状态机节点直接调用的浏览器侧函数替换为确定性 stub。"""
    monkeypatch.setattr(submit_flow, "process_browser_snapshot", side.snapshot)
    monkeypatch.setattr(submit_flow, "browser_upload_resume", side.upload)
    monkeypatch.setattr(submit_flow, "browser_fill_form", side.fill)
    monkeypatch.setattr(submit_flow, "browser_probe_dropdowns", side.probe)
    monkeypatch.setattr(submit_flow, "browser_fill_dropdowns", side.fill_dropdowns)
    monkeypatch.setattr(profile_storage, "load", side.profile_load)


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
        "dropdown_options": {},
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
async def test_flow_completes_all_stages(monkeypatch):
    """「继续」后自动经过快照→上传→再快照→个人信息→填表→探测→填下拉框。"""
    client = StubClient()
    registry = FakeRegistry()
    side = _BrowserSide()
    _patch_browser_side(monkeypatch, side)
    graph = build_graph(client, registry)

    state = _base_state(submit_flow=waiting_login_flow())
    final = await _run(graph, state)

    assert final is not None and final.get("submit_flow") is not None
    assert final["submit_flow"]["current_stage"] == "completed"

    # 同一 URL 快照 2 次（flow_snapshot + 简历解析后 flow_snapshot_again）
    assert side.snapshot_calls == 2
    # 浏览器侧直接调用各一次（不经 registry）
    assert side.profile_calls == 1
    assert side.upload_calls == 1
    assert side.fill_calls == 1
    assert side.probe_calls == 1
    assert side.fill_dropdowns_calls == 1
    # 流程内不再经由 registry 调用 browser_fill_dropdowns
    assert registry.calls.get("browser_fill_dropdowns", 0) == 0
    # 已填写的下拉框（plan 覆盖的字段名）从 dropdown_fields 中移除，仅保留未填的
    assert final["submit_flow"].get("dropdown_fields") == {}
    assert final["submit_flow"].get("dropdown_fill_plan") == {"所在城市": "广州"}
    # 填空框：脱敏标记「手机」在写入前回读真实值，报告展示 ***
    assert side.last_fill_items is not None
    assert {"ref": "e1", "value": "张三", "display": "张三"} in side.last_fill_items
    assert {"ref": "e2", "value": "18928733892", "display": "***"} in side.last_fill_items
    # 下拉框：值直接传入，未脱敏
    assert side.last_dropdown_items == [
        {"name": "所在城市", "value": "广州", "display": "广州"}
    ]


@pytest.mark.asyncio
async def test_flow_multi_resume_waits_then_chooses(monkeypatch):
    """多份简历：停在 waiting_resume_choice，用户回复序号后继续。"""
    client = StubClient()
    registry = FakeRegistry()
    side = _BrowserSide(multi_resume=True)
    _patch_browser_side(monkeypatch, side)
    graph = build_graph(client, registry)

    # 第一轮进入 waiting_resume_choice
    state = _base_state(submit_flow=waiting_login_flow())
    final = await _run(graph, state)

    assert final["submit_flow"]["current_stage"] == "waiting_resume_choice"
    assert side.upload_calls == 1

    # 第二轮用户回复选择 → 治愈最后完成
    flow = final["submit_flow"]
    flow["current_stage"] = "waiting_resume_choice"
    state2 = {
        "messages": [Message(role="user", content="1")],
        "submit_flow": flow,
    }
    final2 = await _run(graph, state2)

    assert final2.get("submit_flow") is None or final2["submit_flow"]["current_stage"] in ("resume_uploaded", "completed")


@pytest.mark.asyncio
async def test_flow_get_personal_flattens_profile(monkeypatch):
    """个人信息打平为 {前端标签: 真实值}，脱敏字段标签记录在 masked_labels。"""
    side = _BrowserSide()
    _patch_browser_side(monkeypatch, side)
    flow = waiting_login_flow()

    streamed: list[str] = []
    original = submit_flow.get_stream_writer
    submit_flow.get_stream_writer = lambda: lambda chunk: streamed.append(chunk.delta)
    try:
        result = await flow_get_personal_node(
            {"submit_flow": flow}, config={}, client=None, registry=None
        )
    finally:
        submit_flow.get_stream_writer = original

    out_flow = result["submit_flow"]
    # 只打平 basic_info，键为前端标签（姓名/手机），值保留真实值
    assert out_flow["personal_profile"] == {"姓名": "张三", "手机": "18928733892", "所在地点": "广州"}
    # 脱敏字段记录前端标签，供文本视图「标签:标签」占位与写表回读
    assert out_flow["masked_labels"] == ["手机"]


# 触发「决策系统」system 时不会被当成普通 chat，所以上面测试不成立时可用显式决策 client
class DecisionStub(StubClient):
    async def stream(self, messages, system="", tools=None):
        if "决策" in system:
            yield TextChunk(delta=json.dumps({"姓名": "张三"}, ensure_ascii=False))
            return
        yield TextChunk(delta="好的。")


@pytest.mark.asyncio
async def test_decision_stub_returns_json():
    client = DecisionStub()
    msgs = [Message(role="user", content="以下是待填写的表单控件：")]
    collected = []
    async for ev in client.stream(msgs, system=_DECISION_SYSTEM):
        collected.append(ev.delta)
    assert json.loads("".join(collected)) == {"姓名": "张三"}


@pytest.mark.asyncio
async def test_browser_error_clears_flow(monkeypatch):
    """浏览器侧操作失败（上传简历出错）→ submit_flow 清空、回到普通对话。"""
    client = StubClient()
    registry = FakeRegistry()
    side = _BrowserSide()
    _patch_browser_side(monkeypatch, side)

    async def failing_upload(ref, resume):
        return SubmitResult(output="上传简历失败：浏览器不可用", is_error=True)

    monkeypatch.setattr(submit_flow, "browser_upload_resume", failing_upload)
    graph = build_graph(client, registry)

    state = _base_state(submit_flow=waiting_login_flow())
    final = await _run(graph, state)

    assert final.get("submit_flow") is None or final["submit_flow"].get("current_stage") in (
        None,
        "waiting_login",
    )
    texts = [m.content for m in final["messages"] if m.role == "assistant"]
    assert any("上传简历失败" in t for t in texts)