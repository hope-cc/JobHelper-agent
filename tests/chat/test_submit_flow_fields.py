"""单测：用 example/snapshot1.txt、snapshot2.txt 驱动「三类字段字典」解析。

运行（在项目根目录下）：
    D:/coding/Anaconda/envs/agent/python.exe tests/chat/test_submit_flow_fields.py
或
    pytest tests/chat/test_submit_flow_fields.py -s
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

SNAPSHOTS = {
    "snapshot1": ROOT / "example" / "snapshot1.txt",
    "snapshot2": ROOT / "example" / "snapshot2.txt",
}


def parse(name: str) -> dict:
    return parse_snapshot_fields(SNAPSHOTS[name].read_text(encoding="utf-8"))


def show(name: str) -> str:
    groups = parse(name)
    lines = [name]
    for key, title in (
        ("textboxes", "填空 textbox"),
        ("dropdowns", "下拉框 [cursor=pointer]"),
        ("uploads", "简历上传"),
    ):
        d = groups[key]
        lines.append(f"\n[{title}] {len(d)} 个")
        for field, ref in d.items():
            lines.append(f"  {field} -> {ref}")
    return "\n".join(lines)


def test_snapshot1_textboxes():
    tb = parse("snapshot1")["textboxes"]
    assert tb["姓名"] == "e168"
    assert tb["手机号码"] == "e187"          # 前缀「+86」不影响标签解析
    assert tb["英文名"] == "e195"
    assert tb["邮箱"] == "e219"
    assert tb["证件号码"] == "e286"         # 「身份证」证件类型前缀不影响标签解析
    assert "请输入" not in tb  # 占位词不会被当成字段名
    # 排除下拉框弹层内部的隐藏输入框（e121 / e144 / e261 ...）
    for r in ("e121", "e144", "e261", "e321", "e341", "e518"):
        assert r not in tb.values(), r


def test_snapshot1_dropdowns():
    dd = parse("snapshot1")["dropdowns"]
    assert dd["面试站点"] == "e116"
    assert dd["意向工作地点"] == "e139"
    assert dd["出生日期"] == "e257"
    assert dd["籍贯"] == "e298"
    assert dd["英语等级"] == "e337"
    assert dd["最高学历"] == "e421"
    assert dd["学历"] == "e623"
    assert dd["学习方式Education Type"] == "e769"
    # 「添加教育经历」等展开按钮不算下拉框
    assert all(r not in dd.values() for r in ("e780", "e918", "e1006"))
    # 侧边导航 tab 不算下拉框
    assert "e1703" not in dd.values()


def test_snapshot1_uploads():
    up = parse("snapshot1")["uploads"]
    assert up["上传简历"] == "e88"          # 拖拽上传区
    assert up["证件照"] == "e201"
    assert up["英语等级文件上传"] == "e360"
    assert up["最高学历成绩单(PDF附件小于5M)"] == "e540"
    assert up["简历附件"] == "e801"
    # 侧边「上传简历」导航 tab 不是上传入口
    assert len(up) == 5


def test_snapshot2_fields():
    p = parse("snapshot2")
    tb, dd, up = p["textboxes"], p["dropdowns"], p["uploads"]
    assert tb["姓名"] == "e112"
    assert tb["邮箱"] == "e126"
    assert tb["年龄"] == "e146"
    assert tb["专业"] == "e288"
    assert tb["自我评价"] == "e361"
    # 「期望工作地点」下拉框内的 filter select 输入框被排除
    assert "filter select" not in tb and "e204" not in tb.values()
    assert dd["性别"] == "e134"
    assert dd["所在地点"] == "e154"
    assert dd["个人证件"] == "e171"
    assert dd["家乡"] == "e187"
    assert dd["期望工作地点"] == "e199"
    assert dd["学校名称"] == "e245"
    assert dd["学历"] == "e259"
    assert dd["学历类型"] == "e274"
    # 拖拽区按钮只保留最外层入口；「提交简历」不算上传
    assert up["附件简历"] == "e91"
    assert "e96" not in up.values() and "e376" not in up.values()


def _dump_test():
    out = [show("snapshot1"), show("snapshot2")]
    return "\n\n====================\n\n".join(out)


class FakeRegistry:
    """假注册器：browser_snapshot 直接返回快照 txt 的内容。"""

    def __init__(self, name: str):
        self.name = name

    async def execute(self, name: str, arguments: dict | None = None) -> ToolResult:
        return ToolResult(output=SNAPSHOTS[self.name].read_text(encoding="utf-8"))


async def _call_node(name: str) -> dict:
    """在图外直接调用 flow_snapshot_node；替换流式 writer 为收集器。"""
    streamed: list[str] = []
    original = submit_flow.get_stream_writer
    submit_flow.get_stream_writer = lambda: lambda chunk: streamed.append(chunk.delta)
    try:
        # 真实节点直接调浏览器 MCP；此处用 fixture 文案解析结果喂给节点
        groups = parse_snapshot_fields(SNAPSHOTS[name].read_text(encoding="utf-8"))

        async def fake_snapshot():
            return groups["textboxes"], groups["dropdowns"], groups["uploads"]

        original_snapshot = submit_flow.process_browser_snapshot
        submit_flow.process_browser_snapshot = fake_snapshot
        try:
            result = await flow_snapshot_node(
                {"submit_flow": new_submit_flow("job.example.com/x")},
                config={},
                client=None,
                registry=FakeRegistry(name),
            )
        finally:
            submit_flow.process_browser_snapshot = original_snapshot
    finally:
        submit_flow.get_stream_writer = original
    return result


async def run_node_test() -> str:
    parts = []
    for name in SNAPSHOTS:
        result = await _call_node(name)
        flow = result["submit_flow"]
        summary = (
            f"[{name}]\n"
            f"stage={flow['current_stage']}\n"
            f"textbox_fields={json.dumps(flow.get('textbox_fields'), ensure_ascii=False)}\n"
            f"dropdown_fields={json.dumps(flow.get('dropdown_fields'), ensure_ascii=False)}\n"
            f"upload_fields={json.dumps(flow.get('upload_fields'), ensure_ascii=False)}\n"
            f"unfilled={len(flow.get('unfilled_fields'))} has_upload={flow.get('has_upload_entry')}\n"
            f"msg={result['messages'][-1].content}"
        )
        parts.append(summary)
    return "\n\n".join(parts)


def test_node_parses_both_snapshots():
    out = asyncio.run(run_node_test())
    assert "snapshot1" in out and "snapshot2" in out
    # 节点输出“已识别投递表单”汇总（current_stage 由流程其余逻辑推进）
    assert "已识别投递表单" in out


if __name__ == "__main__":
    print(_dump_test())
    print("\n\n==================== 节点级 ====================\n")
    print(asyncio.run(run_node_test()))