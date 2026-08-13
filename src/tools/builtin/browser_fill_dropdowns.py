"""browser_fill_dropdowns 工具：按 {ref, 目标值} 填写投递表单下拉框。

采用分层自适应策略，覆盖不同站点形态：
1. 展开后快照里有可点击选项（原生 select / zhiye 型）→ 匹配 ref 直接点击；
2. 展开后无选项但带过滤输入框（过滤型 combobox）→ 向输入框输入目标值触发搜索，
   重新快照若有选项 ref 则点击，否则 browser_find / JS 按文本点击选项，最后点击「确定/确认」按钮；
3. 无过滤输入框 → browser_find / JS 直接按文本点击可见选项。
"""

from pydantic import BaseModel, Field

from src.api import profile_storage
from src.browser_mcp.client import call_tool
from src.browser_mcp.dropdown import (
    FILTER_WAIT_SECONDS,
    click_text,
    crop_subtree,
    expand_and_crop,
    extract_options,
    find_confirm_button_ref,
    find_dropdown_candidates,
    find_filter_input,
    find_option_ref,
    select_by_text,
)
from src.browser_mcp.fill import display_value, resolve_profile_value
from src.tools import ToolResult, tool

import asyncio


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


async def _confirm_select(snap_text: str) -> None:
    """过滤型路径选完后点「确定/确认」按钮（该站点需要点确定才生效）。"""
    confirm_ref = find_confirm_button_ref(snap_text)
    if not confirm_ref:
        fresh, _ = await call_tool("browser_snapshot", {})
        confirm_ref = find_confirm_button_ref(fresh)
    if confirm_ref:
        await _click_ref(confirm_ref)


@tool(
    name="browser_fill_dropdowns",
    description=(
        "按 ref+目标值 映射填写投递表单的下拉选择框。程序先校验传入 ref 是否为有效下拉框"
        "（无效项跳过不点击，避免误触按钮）。对不同类型的下拉框自适应：选项在快照中可直接点击的用 ref 点击；"
        "带过滤输入框的会先输入目标值触发搜索，再点击过滤出的选项并点「确定」；"
        "其余情况按文本定位选项点击。目标值可通过 data_key（后台解析真实值，敏感字段返回时显示 ***）"
        "或字面量 value 指定。返回已填/未匹配/失败/跳过报告。ref 来自 browser_probe_dropdowns。"
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

        cropped, cerr = await expand_and_crop(ref)
        if cerr:
            failed.append({"ref": ref, "reason": _scrub(cerr, value, display)})
            continue

        # ---- 路径 1：展开快照里有选项 ----
        opts = extract_options(cropped)
        if opts:
            opt_ref, matched = find_option_ref(opts, value)
            if opt_ref:
                res, rerr = await _click_ref(opt_ref)
                if rerr:
                    failed.append({"ref": ref, "reason": _scrub(res, value, display)})
                else:
                    filled.append({"ref": ref, "value": display})
                continue
            if matched is None:
                unmatched.append({"ref": ref, "reason": f"目标值「{display}」不在选项中"})
                continue
            # 选项存在但不可点击 → 文本定位/JS 兜底
            ok, msg = await select_by_text(value)
            if ok:
                filled.append({"ref": ref, "value": display})
            else:
                unmatched.append({"ref": ref, "reason": f"选项「{display}」不可点击且按文本选中失败：{msg}"})
            continue

        # ---- 路径 2：过滤型 combobox（无选项但有过滤输入框）----
        filter_ref = find_filter_input(cropped)
        if filter_ref:
            t, e = await call_tool("browser_type", {"target": filter_ref, "text": value})
            if e:
                failed.append({"ref": ref, "reason": _scrub(t, value, display)})
                continue
            await asyncio.sleep(FILTER_WAIT_SECONDS)

            snap2, e2 = await call_tool("browser_snapshot", {})
            if e2:
                failed.append({"ref": ref, "reason": f"过滤后快照失败：{snap2}"})
                continue
            cropped2 = crop_subtree(snap2, ref) or cropped
            opts2 = extract_options(cropped2)
            opt_ref2, matched2 = find_option_ref(opts2, value) if opts2 else (None, None)

            if opt_ref2:
                await _click_ref(opt_ref2)
            elif matched2 is None:
                ok, msg = await select_by_text(value)
                if not ok:
                    unmatched.append({"ref": ref, "reason": f"过滤后无法选中目标值「{display}」：{msg}"})
                    continue
            # 点确定（若存在）
            await _confirm_select(snap2)
            filled.append({"ref": ref, "value": display})
            continue

        # ---- 路径 3：无选项也无过滤输入框 → 按文本定位 ----
        ok, msg = await select_by_text(value)
        if ok:
            filled.append({"ref": ref, "value": display})
        else:
            unmatched.append({"ref": ref, "reason": f"无法选中目标值「{display}」：{msg}"})

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
