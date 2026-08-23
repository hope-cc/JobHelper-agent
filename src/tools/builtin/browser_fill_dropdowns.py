"""browser_fill_dropdowns 工具：按 {ref, 目标值} 填写投递表单下拉框。

分层自适应策略（兼容多种站点弹层交互）：
- 路径 1（点选）：展开后从弹层取选项，匹配目标值直接点击选项（优先其「圆圈」ref，失败回退文本 ref），
  弹层内有「确定/确认」则补齐点击。
- 路径 2（过滤+点选）：弹层内带搜索框时，输入目标值触发过滤 → 重新全局快照 → 再次匹配并点击 → 确定。
- 路径 3（过滤+回车）：过滤后仍无可见选项时，按回车（MCP 键盘事件，JS 兜底）→ 重新快照匹配并点击/确定。
- 路径 4（文本兜底）：未定位到弹层时，用 browser_find / JS 按文本点击可见选项。

动作成功（点击/回车无工具错误）即视为填好。目标值可通过 data_key（后台解析真实值，敏感字段返回 ***）
或字面量 value 指定。ref 来自 browser_probe_dropdowns 返回。
"""

import asyncio

from pydantic import BaseModel, Field

from src.api import profile_storage
from src.browser_mcp.client import call_tool
from src.browser_mcp.dropdown import (
    FILTER_WAIT_SECONDS,
    _snapshot_global,
    click_option_ref,
    close_popup,
    expand_popup,
    find_dropdown_candidates,
    find_popup,
    match_option,
    popup_confirm_ref,
    popup_filter_ref,
    popup_options,
    press_enter,
    select_by_text,
)
from src.browser_mcp.fill import display_value, resolve_profile_value
from src.tools import ToolResult, tool


class DropdownFill(BaseModel):
    """单个下拉框与目标值的映射。"""

    ref: str = Field(..., description="下拉框 ref（来自 browser_probe_dropdowns 返回）")
    data_key: str = Field(
        default="",
        description=(
            "个人信息数据键（如 basic_info.name）。与 value 二选一，优先使用；"
            "敏感字段在返回内容中以 *** 显示。"
        ),
    )
    value: str = Field(default="", description="要选择的选项文本。提供 data_key 时忽略。")


class Params(BaseModel):
    items: list[DropdownFill] = Field(
        ...,
        description="要填写的下拉框与目标值映射列表",
    )


def _scrub(text: str, real: str, display: str) -> str:
    """把错误文本中的真实值替换为脱敏显示值，防止敏感值泄露到返回内容。"""
    if real and display and real != display:
        return text.replace(real, display)
    return text


async def _click_ref(target: str) -> tuple[str, bool]:
    try:
        return await call_tool("browser_click", {"target": target})
    except Exception as exc:
        return str(exc), True


async def _confirm_popup(popup: dict) -> None:
    """选完后点弹层「确定/确认」（该站点需点确定才生效），失败不阻塞。"""
    confirm_ref = popup_confirm_ref(popup)
    if confirm_ref:
        await _click_ref(confirm_ref)


async def _pick_filtered(ref: str, popup: dict, value: str, display: str):
    """在弹层内输入过滤词并重新匹配选项（路径 2 与 3 共用）。返回 (是否选中, 说明)。"""
    filter_ref = popup_filter_ref(popup)
    if not filter_ref or not value:
        return False, "弹层内无过滤输入框"

    t, e = await call_tool("browser_type", {"target": filter_ref, "text": value})
    if e:
        return False, f"输入过滤词失败：{t}"
    await asyncio.sleep(FILTER_WAIT_SECONDS)

    snap, e2 = await _snapshot_global()
    if e2:
        return False, f"过滤后快照失败：{snap}"

    popup2 = find_popup(snap, ref)
    if popup2 is not None:
        target2 = match_option(popup_options(popup2), value)
        if target2 is not None:
            ok, msg = await click_option_ref(target2)
            if ok:
                await _confirm_popup(popup2)
                await close_popup(ref, popup2)
                return True, msg

    # 过滤后仍无可见匹配 → 按回车再试（路径 3）
    await press_enter()
    await asyncio.sleep(FILTER_WAIT_SECONDS)

    snap3, e3 = await _snapshot_global()
    if not e3:
        popup3 = find_popup(snap3, ref)
        if popup3 is not None:
            target3 = match_option(popup_options(popup3), value)
            if target3 is not None:
                ok3, msg3 = await click_option_ref(target3)
                if ok3:
                    await _confirm_popup(popup3)
                    await close_popup(ref, popup3)
                    return True, msg3
    return False, None


async def _fill_via_popup(ref: str, value: str) -> tuple[bool, str]:
    """多路径尝试在弹层内选中目标值。返回 (是否选中, 说明)。"""
    # ---- L1：展开 + 直接点选 ----
    popup, err = await expand_popup(ref)
    if err:
        # 弹层未出现 → L4 文本兜底
        return await select_by_text(value)

    target = match_option(popup_options(popup), value)
    if target is not None:
        ok, msg = await click_option_ref(target)
        if ok:
            await _confirm_popup(popup)
            await close_popup(ref, popup)
            return True, msg
        # 点击失败继续走过滤路径

    # ---- L2/L3：过滤输入 + 点选 / 回车 ----
    ok2, _ = await _pick_filtered(ref, popup, value)
    if ok2:
        return True, "过滤后选中"

    # ---- L4：文本兜底 ----
    ok4, msg4 = await select_by_text(value)
    if ok4:
        await close_popup(ref, popup)
        return True, msg4

    await close_popup(ref, popup)
    return False, f"展开后未匹配到「{value}」，且按文本选中失败：{msg4}"


@tool(
    name="browser_fill_dropdowns",
    description=(
        "按 ref+目标值 映射填写投递表单的下拉选择框。程序先校验传入 ref 是否为有效下拉框"
        "（无效项跳过不点击，避免误触按钮）。对不同类型的下拉框自适应：选项在展开弹层中可直接点击的用「圆圈/文本」点击；"
        "弹层带过滤输入框的会先输入目标值触发搜索，再点击过滤出的选项并点「确定」；"
        "输入后按回车（部分站点回车后收起）也会尝试；其余情况按文本定位选项点击。"
        "目标值可通过 data_key（后台解析真实值，敏感字段返回时显示 ***）或字面量 value 指定。"
        "返回已填/未匹配/失败/跳过报告。ref 来自 browser_probe_dropdowns。"
    ),
)
async def browser_fill_dropdowns(params: Params):
    profile = profile_storage.load()

    snap, err = await call_tool("browser_snapshot", {})
    if err:
        return ToolResult(output=f"获取快照失败：{snap}", is_error=True)
    candidates = find_dropdown_candidates(snap)
    valid_refs = {c["ref"] for c in candidates}

    filled, unmatched, failed, skipped = [], [], [], []

    for item in params.items:
        ref = item.ref.strip()
        if not ref:
            skipped.append({"ref": "", "reason": "ref 为空"})
            continue
        if ref not in valid_refs:
            skipped.append({"ref": ref, "reason": "无效 ref（非下拉框，未点击）"})
            continue

        # 解析目标值：data_key 优先，其次字面量 value
        if item.data_key:
            value = resolve_profile_value(profile, item.data_key)
            if value is None:
                unmatched.append({"ref": ref, "reason": f"数据键 {item.data_key} 无值"})
                continue
            display = display_value(item.data_key, value, profile)
        else:
            value = item.value
            display = item.value
            if not value:
                unmatched.append({"ref": ref, "reason": "目标值为空"})
                continue

        try:
            ok, reason = await _fill_via_popup(ref, value)
        except Exception as exc:  # 单 item 异常不中断整体
            failed.append({"ref": ref, "reason": _scrub(str(exc), value, display)})
            continue

        if ok:
            filled.append({"ref": ref, "value": display})
        else:
            unmatched.append({"ref": ref, "reason": _scrub(reason, value, display)})

    lines = [
        "下拉框填写结果：",
        f"已填写（{len(filled)}）：",
    ]
    lines += [f"- [{f['ref']}] → {f['value']}" for f in filled]
    lines.append(f"未匹配（{len(unmatched)}）：")
    lines += [f"- [{u['ref']}] {u['reason']}" for u in unmatched]
    lines.append(f"失败（{len(failed)}）：")
    lines += [f"- [{f['ref']}] {f['reason']}" for f in failed]
    lines.append(f"跳过（{len(skipped)}）：")
    lines += [f"- [{s['ref']}] {s['reason']}" for s in skipped]
    return ToolResult(output="\n".join(lines))