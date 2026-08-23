"""browser_probe_dropdowns 工具：逐个展开未填写的下拉框，返回 {ref, label, options}。

实现步骤 7：识别到下拉框后，对每个**未填写**的下拉框（已有值的不展开）逐个执行：
点击展开 → 全局快照定位弹层 → 提取选项纯文本 → 收起弹层 → 处理下一个。
每个下拉框返回 ref、字段标签（label）、当前显示值（display）与选项清单（options）。
选项从弹层中提取，过滤 ref/DOM 结构，只保留文本本身。
"""

import asyncio

from pydantic import BaseModel, Field

from src.browser_mcp.client import call_tool
from src.browser_mcp.dropdown import (
    close_popup,
    expand_popup,
    find_dropdown_candidates,
    popup_option_texts,
)
from src.tools import ToolResult, tool


class Params(BaseModel):
    refs: list[str] = Field(
        default_factory=list,
        description="（可选）限定要探测的下拉框 ref 列表。为空时探测全部未填写的下拉框。",
    )


async def _probe_row(ref: str, label: str, display: str) -> dict:
    """探测单个下拉框：展开、取文本、收起。返回条目字典。"""
    item = {
        "ref": ref,
        "label": label,
        "display": display,
        "options": [],
        "failed": "",
    }
    popup, err = None, ""
    for _ in range(2):  # 首次失败重试一次
        popup, err = await expand_popup(ref)
        if not err:
            break
        await asyncio.sleep(0.3)
    if err:
        item["failed"] = err
    else:
        item["options"] = popup_option_texts(popup)
    # 收起弹层（忽略收起失败，避免影响下一个）——成功展开过才尝试收起
    if not err:
        await close_popup(ref, popup)
    return item


@tool(
    name="browser_probe_dropdowns",
    description=(
        "识别当前页面投递表单中尚未填写的非标准下拉框，逐个展开后返回每个下拉框的 "
        "ref、字段标签和可用选项清单（选项为纯文本，不含 ref/DOM 结构）。"
        "下拉框表现为 combobox 或 generic [cursor=pointer]（子元素显示「请选择」或当前值）。"
        "据此构造 browser_fill_dropdowns 的 items（ref + data_key/value）。"
        "已填写的下拉框不会被展开。可传入 refs 限定探测范围。"
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

    results: list[dict] = []
    for c in unfilled:
        results.append(await _probe_row(c["ref"], c.get("label", ""), c.get("display", "")))

    lines = [f"下拉框探测结果（共 {len(candidates)} 个，未填 {len(unfilled)} 个）："]
    if not candidates:
        lines = ["未在页面快照中识别到下拉框。"]
    else:
        if not unfilled and not requested:
            lines.append("- 没有未填写的下拉框，全部已填写。")
        for r in results:
            label = r["label"] or "(无标签)"
            if r["failed"]:
                lines.append(f"- [{r['ref']}] {label}（未填）：识别失败 - {r['failed']}")
            elif not r["options"]:
                lines.append(f"- [{r['ref']}] {label}（未填）：展开后无可用选项")
            else:
                options = "、".join(r["options"])
                lines.append(f"- [{r['ref']}] {label}（未填）：{options}")
        if filled:
            lines.append("已填（无需处理）：")
            for c in filled:
                lines.append(f"  - [{c['ref']}] {c.get('label') or '(无标签)'}：{c.get('display') or '空'}")

    for r in sorted(unknown):
        lines.append(f"- {r}：无效 ref（不在识别出的下拉框中）")

    return ToolResult(output="\n".join(lines))