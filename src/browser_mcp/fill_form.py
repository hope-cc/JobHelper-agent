"""按 ref+值 映射填写投递表单（原 browser_fill_form 工具搬移版）。

从工具注册中心迁入 browser_mcp：不再暴露为 LLM 可用工具，由投递流程状态机
节点直接调用。值由节点从扁平个人信息解析真实值后直接传入；敏感字段的真实值
由节点以 {"display": "***"} 标记，返回报告不致泄露真实值。
"""

from src.browser_mcp.client import call_tool
from src.browser_mcp.fill import (
    find_radio_ref,
    match_combobox_value,
    parse_snapshot,
)
from src.browser_mcp.types import SubmitResult


def _scrub(text: str, real: str, display: str) -> str:
    """把错误文本中的真实值替换为脱敏显示值，防止敏感值泄露到返回内容。"""
    if real and display and real != display:
        return text.replace(real, display)
    return text


async def browser_fill_form(items: list[dict]) -> SubmitResult:
    """按 [{"ref", "value"}] 映射填写投递表单。

    Args:
        items: [{ref, value}]，值已由调用方（flow_fill_form_node）解析为真实值；
            敏感字段可附带 {"display": "***"} 控制报告中的展示值。

    Returns:
        SubmitResult —— 汇总已填/未匹配/失败报告。
    """
    snap, err = await call_tool("browser_snapshot", {})
    if err:
        return SubmitResult(output=snap, is_error=True)
    elements = parse_snapshot(snap)
    by_ref = {el["ref"]: el for el in elements}

    filled, failed, unmatched = [], [], []

    for item in items:
        ref = item.get("ref", "")
        value = item.get("value", "")
        display = item.get("display") or value
        if not ref or value is None:
            continue
        el = by_ref.get(ref)
        if el is None:
            unmatched.append(
                {"ref": ref, "value": display, "reason": "无效 ref（控件不存在）"}
            )
            continue

        role = el["role"]

        try:
            if role in ("textbox", "textarea", "searchbox"):
                res_text, res_err = await call_tool(
                    "browser_fill_form",
                    {
                        "fields": [
                            {
                                "target": ref,
                                "name": el.get("name") or ref,
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
                            "ref": ref,
                            "value": display,
                            "reason": f"选项不匹配（期望值 {display}）",
                        }
                    )
                    continue
                res_text, res_err = await call_tool(
                    "browser_select_option", {"target": ref, "values": [matched]}
                )
            elif role == "radio":
                target = find_radio_ref(elements, value)
                if target is None:
                    unmatched.append(
                        {
                            "ref": ref,
                            "value": display,
                            "reason": f"未找到对应选项（期望值 {display}）",
                        }
                    )
                    continue
                res_text, res_err = await call_tool("browser_click", {"target": target})
            elif role == "checkbox":
                if el.get("selected"):
                    res_text, res_err = "", False
                else:
                    res_text, res_err = await call_tool("browser_click", {"target": ref})
            else:
                unmatched.append(
                    {"ref": ref, "value": display, "reason": f"不支持的控件类型 {role}"}
                )
                continue
        except Exception as exc:
            failed.append(
                {"ref": ref, "value": display, "reason": f"执行异常: {exc}"}
            )
            continue

        if res_err:
            failed.append(
                {"ref": ref, "value": display, "reason": _scrub(res_text, value, display)}
            )
        else:
            filled.append({"ref": ref, "value": display})

    lines = [
        f"已填写（{len(filled)}）：",
    ]
    lines += [f"- [{f['ref']}] → {f['value']}" for f in filled]
    lines.append(f"未匹配（{len(unmatched)}）：")
    lines += [f"- [{u['ref']}] {u['value']}：{u['reason']}" for u in unmatched]
    lines.append(f"失败（{len(failed)}）：")
    lines += [f"- [{f['ref']}] {f['value']}：{f['reason']}" for f in failed]

    return SubmitResult(output="填写完成：\n" + "\n".join(lines))