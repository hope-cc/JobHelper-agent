"""非标准下拉框选项探测（原 browser_probe_dropdowns 工具的搬移版）。

不再暴露为 LLM 可用工具，改由投递流程状态机节点直接调用：
输入 {字段名: ref}，逐个展开下拉框提取选项，返回 {字段名: [选项文本]}。
探测失败的下拉框返回空列表，不影响其他下拉框探测。
"""

from __future__ import annotations

from src.browser_mcp.dropdown import (
    close_popup,
    expand_popup,
    popup_option_texts,
)


async def _probe_row(ref: str) -> tuple[list[str], str]:
    """展开单个下拉框并提取选项文本。返回 (选项列表, 错误信息)。

    探测失败不重试，直接返回空列表。
    """
    popup, err = await expand_popup(ref)
    if err:
        return [], err
    options = popup_option_texts(popup)
    # 收起弹层（忽略收起失败，避免影响下一个）——成功展开过才尝试收起
    await close_popup(ref, popup)
    return options, ""


async def browser_probe_dropdowns(fields: dict[str, str]) -> dict[str, list[str]]:
    """逐一点击展开下拉框并提取选项，返回 {字段名: [选项]}。

    Args:
        fields: {字段名: ref}（来自快照解析的 dropdown_fields）

    Returns:
        每个字段名到其选项文本列表的字典；探测失败的下拉框选项为空列表。
    """
    result: dict[str, list[str]] = {}
    for name, ref in fields.items():
        options, _err = await _probe_row(ref)
        result[name] = options
    return result