"""browser_fill_form 工具：按 ref+数据键 映射脱敏填写投递表单。"""

from pydantic import BaseModel, Field

from src.api import profile_storage
from src.browser_mcp.client import call_tool
from src.browser_mcp.fill import (
    display_value,
    find_radio_ref,
    match_combobox_value,
    parse_snapshot,
    resolve_profile_value,
)
from src.tools import ToolResult, tool


class FillItem(BaseModel):
    """单个控件与个人信息数据键的映射。"""

    ref: str = Field(..., description="控件 ref（来自 browser_snapshot）")
    data_key: str = Field(
        ...,
        description=(
            "个人信息数据键，如 basic_info.name、basic_info.id_number、"
            "education[0].school_name、self_evaluation。可先调用 getPersonalInfo 查看可用数据键。"
        ),
    )


class Params(BaseModel):
    items: list[FillItem] = Field(
        ...,
        description="要填写的控件与个人信息数据键的映射列表",
    )


def _scrub(text: str, real: str, display: str) -> str:
    """把错误文本中的真实值替换为脱敏显示值，防止敏感值泄露到返回内容。"""
    if real and display and real != display:
        return text.replace(real, display)
    return text


@tool(
    name="browser_fill_form",
    description=(
        "按 ref+数据键 的映射填写投递表单。后台从本地个人信息读取真实值并调用浏览器填写，"
        "返回已填/失败/未匹配报告；敏感字段（如证件号）在返回内容中以 *** 显示，不泄露真实值。"
        "应先调用 getPersonalInfo 查看可用的数据键，再据此构造 items。"
    ),
)
async def browser_fill_form(params: Params):
    profile = profile_storage.load()
    if profile is None:
        return ToolResult(
            output="尚未保存个人信息，请先在「个人信息管理」页面填写并保存后再调用。",
            is_error=True,
        )

    snap, err = await call_tool("browser_snapshot", {})
    if err:
        return ToolResult(output=snap, is_error=True)
    elements = parse_snapshot(snap)
    by_ref = {el["ref"]: el for el in elements}

    filled, failed, unmatched = [], [], []

    for item in params.items:
        el = by_ref.get(item.ref)
        if el is None:
            unmatched.append(
                {"ref": item.ref, "data_key": item.data_key, "reason": "无效 ref（控件不存在）"}
            )
            continue

        value = resolve_profile_value(profile, item.data_key)
        if value is None:
            unmatched.append(
                {"ref": item.ref, "data_key": item.data_key, "reason": "数据键无值"}
            )
            continue

        display = display_value(item.data_key, value, profile)
        role = el["role"]

        try:
            if role in ("textbox", "textarea", "searchbox"):
                res_text, res_err = await call_tool(
                    "browser_fill_form",
                    {
                        "fields": [
                            {
                                "target": item.ref,
                                "name": el.get("name") or item.data_key,
                                "type": "textbox",
                                "value": value,
                            }
                        ]
                    },
                )
            elif role == "combobox":
                matched = match_combobox_value(el.get("options", []), value)
                if matched is None:
                    unmatched.append(
                        {
                            "ref": item.ref,
                            "data_key": item.data_key,
                            "reason": f"选项不匹配（期望值 {display}）",
                        }
                    )
                    continue
                res_text, res_err = await call_tool(
                    "browser_select_option", {"target": item.ref, "values": [matched]}
                )
            elif role == "radio":
                target = find_radio_ref(elements, value)
                if target is None:
                    unmatched.append(
                        {
                            "ref": item.ref,
                            "data_key": item.data_key,
                            "reason": f"未找到对应选项（期望值 {display}）",
                        }
                    )
                    continue
                res_text, res_err = await call_tool("browser_click", {"target": target})
            elif role == "checkbox":
                if el.get("selected"):
                    res_text, res_err = "", False
                else:
                    res_text, res_err = await call_tool("browser_click", {"target": item.ref})
            else:
                unmatched.append(
                    {"ref": item.ref, "data_key": item.data_key, "reason": f"不支持的控件类型 {role}"}
                )
                continue
        except Exception as exc:
            failed.append(
                {"ref": item.ref, "data_key": item.data_key, "reason": f"执行异常: {exc}"}
            )
            continue

        if res_err:
            failed.append(
                {"ref": item.ref, "data_key": item.data_key, "reason": _scrub(res_text, value, display)}
            )
        else:
            filled.append({"ref": item.ref, "data_key": item.data_key, "value": display})

    lines = [
        f"已填写（{len(filled)}）：",
    ]
    lines += [f"- [{f['ref']}] {f['data_key']} → {f['value']}" for f in filled]
    lines.append(f"未匹配（{len(unmatched)}）：")
    lines += [f"- [{u['ref']}] {u['data_key']}：{u['reason']}" for u in unmatched]
    lines.append(f"失败（{len(failed)}）：")
    lines += [f"- [{f['ref']}] {f['data_key']}：{f['reason']}" for f in failed]

    return ToolResult(output="填写完成：\n" + "\n".join(lines))
