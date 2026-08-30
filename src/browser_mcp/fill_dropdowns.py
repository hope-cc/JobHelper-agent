"""按下拉框字段名填写投递表单（原 browser_fill_dropdowns 工具的搬移版）。

不再暴露为 LLM 可用工具，改由投递流程状态机节点直接调用。
输入为字段名维度的决策计划（items，元素形如 {name, value}）+
字段名→ref 映射（dropdown_fields）。对每个待填下拉框：

    点击下拉框展开 → 从弹层提取可选项 → 匹配目标值 → 点击目标选项

采用「简单路径」：只做展开 + 点选，不做过滤输入/回车/文本兜底等自适应策略；
匹配失败即计入未匹配。目标值由调用方（flow_fill_dropdowns_node）解析真实值后
直接传入；敏感字段的真实值由节点以 {"display": "***"} 标记，返回报告不致泄露。
"""

from __future__ import annotations

from src.browser_mcp.dropdown import (
    click_option_ref,
    expand_popup,
    match_option,
    popup_options,
)
from src.browser_mcp.types import SubmitResult


def _scrub(text: str, real: str, display: str) -> str:
    """把错误文本中的真实值替换为脱敏显示值，防止敏感值泄露到返回内容。"""
    if real and display and real != display:
        return text.replace(real, display)
    return text


async def _select_via_popup(ref: str, value: str) -> tuple[bool, str]:
    """展开下拉框并点选目标选项。返回 (是否选中, 说明)。"""
    popup, err = await expand_popup(ref)
    if err:
        return False, err
    target = match_option(popup_options(popup), value)
    if target is None:
        return False, f"弹层中未匹配到选项「{value}」"
    ok, msg = await click_option_ref(target)
    return ok, msg


async def browser_fill_dropdowns(
    items: list[dict],
    dropdown_fields: dict[str, str],
) -> SubmitResult:
    """按字段名填写投递表单下拉框。

    Args:
        items: [{name, value}] 字段名维度填写计划（flow_fill_dropdowns_node 传入，
            值已解析为真实值；敏感字段可附带 {"display": "***"}）。
        dropdown_fields: {字段名: ref}（来自快照解析的 dropdown_fields）。

    Returns:
        SubmitResult —— 汇总已填/未匹配/失败报告。
    """
    filled, unmatched, failed = [], [], []

    for item in items:
        name = (item.get("name") or "").strip()
        ref = dropdown_fields.get(name, "")
        value = item.get("value")
        display = item.get("display") or value
        if not name or not ref:
            unmatched.append({"name": name, "reason": "字段名不在 dropdown_fields 中（无对应 ref）"})
            continue
        if not value:
            unmatched.append({"name": name, "reason": "目标值为空"})
            continue

        try:
            ok, reason = await _select_via_popup(ref, value)
        except Exception as exc:  # 单字段异常不中断整体
            failed.append({"name": name, "reason": _scrub(str(exc), value, display)})
            continue

        if ok:
            filled.append({"name": name, "value": display})
        else:
            unmatched.append({"name": name, "reason": _scrub(reason, value, display)})

    lines = [
        "下拉框填写结果：",
        f"已填写（{len(filled)}）：",
    ]
    lines += [f"- [{f['name']}] → {f['value']}" for f in filled]
    lines.append(f"未匹配（{len(unmatched)}）：")
    lines += [f"- [{u['name']}] {u['reason']}" for u in unmatched]
    lines.append(f"失败（{len(failed)}）：")
    lines += [f"- [{f['name']}] {f['reason']}" for f in failed]
    return SubmitResult(output="\n".join(lines))