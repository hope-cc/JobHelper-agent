"""投递流程中的 LLM 决策点。

状态机将两个需要语义理解的地方（表单控件 → 个人信息值、下拉选项 → 个人信息值）
交给一次**受控 LLM 调用**：LLM 不接触浏览器、不驱动工具，只根据传入的
控件/下拉框 + 扁平个人信息文本产出 `{控件: 值}` 的 JSON 计划，再由节点执行。

个人信息以扁平视图传入：`personal_profile` 为 `{前端字段标签: 真实值}`，
敏感字段的文本视图显示为「标签:标签」，保证真实值不落提示词。

本模块只做「构造提示 → 调用 LLM → 解析 JSON」三件事。
"""

from __future__ import annotations

import json
import re

from src.llm.base import BaseLLMClient
from src.llm.types import Message, TextChunk

# 决策提示的 system prompt：要求只输出 JSON
_DECISION_SYSTEM = (
    "你是表单自动填写的决策助手。你的任务是根据用户给出的「表单控件」和「个人信息视图」，"
    "确定每个控件该填什么。只能输出一个 JSON 对象，不要加任何解释或前后缀文字。"
)


async def _collect_text(client: BaseLLMClient, system: str, user: str) -> str:
    """调用 LLM 流式接口，收集纯文本输出（不透传给前端）。"""
    parts: list[str] = []
    async for event in client.stream(
        messages=[Message(role="user", content=user)],
        system=system,
        tools=None,
    ):
        if isinstance(event, TextChunk):
            parts.append(event.delta)
    return "".join(parts)


async def collect_decision(client: BaseLLMClient, user: str) -> str:
    """调决策 LLM，返回原始输出文本；出错返回空串。"""
    try:
        return await _collect_text(client, _DECISION_SYSTEM, user)
    except Exception:
        return ""


def extract_json_object(text: str) -> dict | None:
    """从 LLM 输出中提取 JSON 对象（填写计划）；无法解析返回 None。

    兼容三种形态：
    - 纯 JSON 对象文本
    - ```json ... ``` 代码块包裹
    - 文本中混杂一段 JSON 对象（截取首尾大括号）
    """
    if not text:
        return None
    # 去掉代码块围栏
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    t = text.strip()
    if not t:
        return None
    # 纯对象文本
    if t.startswith("{"):
        try:
            obj = json.loads(t)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass
    # 截取首尾大括号
    start = t.find("{")
    end = t.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(t[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def build_profile_text(personal_profile: dict, masked_labels: list[str]) -> str:
    """把扁平个人信息生成多行文本：`字段:值`，脱敏字段显示「标签:标签」。

    Args:
        personal_profile: {前端字段标签: 真实值}（flow_get_personal_node 产出）。
        masked_labels: 脱敏字段的标签列表。

    Returns:
        形如 `姓名:张三\n手机:手机\n邮箱:cc@x.com` 的文本；脱敏字段值以标签占位。
        空值字段不出现。
    """
    masked = set(masked_labels or [])
    lines: list[str] = []
    for label, value in (personal_profile or {}).items():
        if value is None or value == "":
            continue
        if label in masked:
            lines.append(f"{label}:{label}")
        else:
            lines.append(f"{label}:{value}")
    return "\n".join(lines)


async def decide_fill_plan(
    client: BaseLLMClient,
    text_box: dict[str, str],
    personal_profile: dict,
    masked_labels: list[str],
) -> dict:
    """决策：未填填空字段 → {控件标签: 值} 的填写计划。

    Args:
        text_box: {字段名: ref}（快照节点产出的未填填空字段索引）。
        personal_profile: {前端字段标签: 真实值} 扁平个人信息。
        masked_labels: 脱敏字段标签列表（文本视图以「标签:标签」占位）。

    Returns:
        非空 plan 返回字段名维度映射字典；无可填字段/解析失败返回 {}。
    """
    fields_text = "\n".join(f'- "{name}"' for name in text_box) or "(无待填字段)"

    user = (
        "以下是待填写的表单控件标签：\n" + fields_text + "\n\n"
        "以下是可用的个人信息（字段:值，脱敏字段显示为 字段:字段）：\n"
        + build_profile_text(personal_profile, masked_labels) + "\n\n"
        "请为每个需要填写的控件输出 JSON 对象：{\"控件标签\": \"值\"}。\n"
        "键必须是上述表单控件标签之一，值必须是个人信息中的值（脱敏字段直接填其标签）。\n"
        "若某控件在个人信息中没有对应字段，则忽略它不输出。\n"
        "只能输出一个 JSON 对象，不要输出数组或多余文字。"
    )

    raw = await collect_decision(client, user)
    obj = extract_json_object(raw)
    if not obj:
        return {}

    plan: dict = {}
    for name, value in obj.items():
        name = str(name).strip()
        value = str(value).strip()
        if not name or not value:
            continue
        if name not in text_box:  # 只采纳真实存在的控件标签
            continue
        plan[name] = value
    return plan


async def decide_dropdown_plan(
    client: BaseLLMClient,
    dropdown_options: dict[str, list[str]],
    personal_profile: dict,
    masked_labels: list[str],
) -> dict:
    """决策：非标准下拉框 → {下拉框字段名: 值} 填写计划。

    Args:
        dropdown_options: {字段名: [选项文本]}（probe 节点写入 submit_flow 的探测结果）。
        personal_profile: {前端字段标签: 真实值} 扁平个人信息。
        masked_labels: 脱敏字段标签列表（文本视图以「标签:标签」占位）。

    Returns:
        非空 plan 返回字段名维度映射字典；无可填字段/解析失败返回 {}。
    """
    dropdowns_text = "\n".join(
        f'- name="{name}" options=[{"、".join(str(o) for o in options[:12])}]'
        for name, options in dropdown_options.items()
    ) or "- 无下拉框"

    user = (
        "以下是待填写的下拉框（含字段名与可选值）：\n" + dropdowns_text + "\n\n"
        "以下是可用的个人信息（字段:值，脱敏字段显示为 字段:字段）：\n"
        + build_profile_text(personal_profile, masked_labels) + "\n\n"
        "请为每个需要填写的下拉框输出 JSON 对象：{\"下拉框字段名\": \"值\"}。\n"
        "值必须是该下拉框可选列表中存在的文本，或个人信息中的值（脱敏字段直接填其标签）。\n"
        "若不确定则忽略该项。\n"
        "只能输出一个 JSON 对象，不要输出数组或多余文字。"
    )

    raw = await collect_decision(client, user)
    obj = extract_json_object(raw)
    if not obj:
        return {}

    plan: dict = {}
    for name, value in obj.items():
        name = str(name).strip()
        value = str(value).strip()
        if not name or not value:
            continue
        if name not in dropdown_options:  # 只采纳探测结果中真实存在的字段名
            continue
        plan[name] = value
    return plan