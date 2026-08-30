"""单测脚本：用真实快照 example/snapshot1.txt 驱动 flow_snapshot_node。

本脚本只做两件事：
1. 把快照 txt 的内容读成 str；
2. 调用 flow_snapshot_node，并把返回结果转换成字符串打印在终端。

运行（在项目根目录下）：
    D:/coding/Anaconda/envs/agent/python.exe tests/chat/test_submit_flow_snapshot.py
或
    pytest tests/chat/test_submit_flow_snapshot.py -s
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.browser_mcp.form_fields import parse_snapshot_fields  # noqa: E402
from src.chat import submit_flow  # noqa: E402
from src.chat.submit_flow import flow_snapshot_node, new_submit_flow  # noqa: E402
from src.tools.types import ToolResult  # noqa: E402

TXT_PATH = ROOT / "example" / "snapshot1.txt"


class FakeRegistry:
    """假注册器：browser_snapshot 直接返回快照 txt 的内容。"""

    async def execute(self, name: str, arguments: dict | None = None) -> ToolResult:
        return ToolResult(output=read_snapshot())


def read_snapshot() -> str:
    """把 txt 的内容读成 str。"""
    return TXT_PATH.read_text(encoding="utf-8")


async def _call_node() -> tuple[dict, list[str]]:
    """调用 flow_snapshot_node；返回（节点返回值, 流式透传文本列表）。"""
    # 图外直接调用时 langgraph 的 get_stream_writer 会报错，替换为收集器
    streamed: list[str] = []
    original = submit_flow.get_stream_writer
    submit_flow.get_stream_writer = lambda: lambda chunk: streamed.append(chunk.delta)
    try:
        # 真实节点直接调浏览器 MCP；此处用 fixture 文案解析结果喂给节点
        groups = parse_snapshot_fields(read_snapshot())

        async def fake_snapshot():
            return groups["textboxes"], groups["dropdowns"], groups["uploads"]

        original_snapshot = submit_flow.process_browser_snapshot
        submit_flow.process_browser_snapshot = fake_snapshot
        try:
            result = await flow_snapshot_node(
                {"submit_flow": new_submit_flow("job.example.com/x")},
                config={},
                client=None,
                registry=FakeRegistry(),
            )
        finally:
            submit_flow.process_browser_snapshot = original_snapshot
    finally:
        submit_flow.get_stream_writer = original
    return result, streamed


def to_json(state: dict) -> str:
    """把节点返回值转成可打印的 JSON 字符串（messages 内的 Message 对象转 dict）。"""
    payload = dict(state)
    payload["messages"] = [
        {"role": m.role, "content": m.content} for m in state.get("messages", [])
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def run() -> str:
    """执行两件事：读 txt → 调 flow_snapshot_node，把结果转成字符串。"""
    read_snapshot()  # 1. 把 txt 的内容读成 str
    result, streamed = await _call_node()  # 2. 调用 flow_snapshot_node
    return f"[流式透传]\n{''.join(streamed)}\n\n[节点返回 JSON]\n{to_json(result)}"


def test_flow_snapshot_with_real_txt():
    """pytest 入口：保证真实快照能被正常解析并输出「已识别投递表单」汇总。"""
    out = asyncio.run(run())
    assert "已识别投递表单" in out


if __name__ == "__main__":
    print(asyncio.run(run()))