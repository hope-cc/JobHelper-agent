"""browser_probe_dropdowns 工具：程序自动识别投递表单下拉框，返回未填写的下拉框清单。

不展开页面、不获取选项——选项（尤其过滤型下拉框）需在 browser_fill_dropdowns
中通过输入目标值选择。本工具只从当前快照识别下拉框候选，供 LLM 构造填写 items。
"""

from pydantic import BaseModel, Field

from src.browser_mcp.client import call_tool
from src.browser_mcp.dropdown import find_dropdown_candidates
from src.tools import ToolResult, tool


class Params(BaseModel):
    refs: list[str] = Field(
        default_factory=list,
        description="（可选）限定要查看的下拉框 ref 列表。为空时返回全部未填写的下拉框。",
    )


@tool(
    name="browser_probe_dropdowns",
    description=(
        "自动识别当前页面投递表单的下拉选择框，返回未填写的下拉框清单（ref、字段标签、当前值）。"
        "下拉框表现为 combobox 或 generic [cursor=pointer]（子元素显示「请选择」或当前值）。"
        "不展开页面、不枚举选项——选项需在 browser_fill_dropdowns 中通过输入目标值选择。"
        "据此构造 browser_fill_dropdowns 的 items（ref + data_key/value）。"
    ),
)
async def browser_probe_dropdowns(params: Params):
    snap, err = await call_tool("browser_snapshot", {})
    if err:
        return ToolResult(output=f"获取快照失败：{snap}", is_error=True)

    candidates = find_dropdown_candidates(snap)
    requested = [r.strip() for r in params.refs if r and r.strip()]
    if requested:
        wanted = set(requested)
        matched = [c for c in candidates if c["ref"] in wanted]
        unknown = wanted - {c["ref"] for c in candidates}
    else:
        matched = candidates
        unknown = set()

    unfilled = [c for c in matched if c["is_empty"]]
    filled = [c for c in matched if not c["is_empty"]]

    lines = [f"下拉框识别结果（共 {len(candidates)} 个，未填 {len(unfilled)} 个）："]
    if not candidates:
        lines = ["未在页面快照中识别到下拉框。"]
    elif requested:
        for c in matched:
            st = "未填" if c["is_empty"] else f"已填（{c['display'] or '空'}）"
            lines.append(f"- [{c['ref']}] {c['label'] or '(无标签)'}：{st}")
    else:
        if not unfilled:
            lines.append("- 没有未填写的下拉框，全部已填写。")
        for c in unfilled:
            lines.append(f"- [{c['ref']}] {c['label'] or '(无标签)'}：未填")
        if filled:
            lines.append("已填（无需处理）：")
            for c in filled:
                lines.append(f"  - [{c['ref']}] {c['label'] or '(无标签)'}：{c['display'] or '空'}")

    for r in sorted(unknown):
        lines.append(f"- {r}：无效 ref（不在识别出的下拉框中）")

    return ToolResult(output="\n".join(lines))
