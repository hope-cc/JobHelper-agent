"""投递流程中的 LLM 决策点。

状态机将两个需要语义理解的地方（把表单控件映射到个人信息数据键、把下拉选项
映射到个人信息值）交给一次**受控 LLM 调用**：LLM 不接触浏览器、不驱动工具，
只根据传入的字段/下拉框 + 脱敏个人信息视图产出 JSON 映射计划，再由节点执行。

本模块只做「构造提示 → 调用 LLM → 解析 JSON」三件事，保证敏感值不落 messages。
"""

from __future__ import annotations

import json
import re

from src.llm.base import BaseLLMClient
from src.llm.types import Message, TextChunk

# 决策提示的 system prompt：要求只输出 JSON
_DECISION_SYSTEM = (
    "你是表单自动填写的决策助手。你的任务是根据用户给出的「表单控件」和「个人信息视图」，"
    "确定每个控件该填什么。只能输出一个 JSON 数组，不要加任何解释或前后缀文字。"
)

# 字段标签 → 个人信息键 的常见映射提示词（用于降低 LLM 幻觉）
_ROLE_HINTS = (
    "提示：个人信息键的基本结构形如 basic_info.name / basic_info.email / "
    "education[0].school_name，优先复用字段标签与键名的语义对应关系。"
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


def extract_json_array(text: str) -> list[dict] | None:
    """从 LLM 输出中提取 JSON 数组；无法解析返回 None。

    兼容三种形态：
    - 纯 JSON 数组文本
    - ```json ... ``` 代码块包裹
    - 文本中混杂一段 JSON 数组（截取首尾方括号）
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
    # 纯数组文本
    if t.startswith("["):
        try:
            arr = json.loads(t)
            return arr if isinstance(arr, list) else None
        except json.JSONDecodeError:
            pass
    # 截取首尾括号
    start = t.find("[")
    end = t.rfind("]")
    if 0 <= start < end:
        try:
            arr = json.loads(t[start:end + 1])
            return arr if isinstance(arr, list) else None
        except json.JSONDecodeError:
            return None
    return None


def _flatten_profile_keys(profile_masked: dict, prefix: str = "") -> list[str]:
    """把脱敏个人信息视图拍平成 data_key 列表：basic_info.name / education[0].school_name。"""
    keys: list[str] = []
    for k, v in profile_masked.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.extend(_flatten_profile_keys(v, path))
        elif isinstance(v, list):
            if v and isinstance(v[0], dict):
                for key in v[0]:
                    keys.append(f"{path}[0].{key}")
                keys.extend(_flatten_profile_keys(v[0], f"{path}[0]"))
            else:
                keys.append(path)
        else:
            keys.append(path)
    return keys


def _compact_profile(profile_masked: dict, max_len: int = 400) -> str:
    """把脱敏个人信息视图压成紧凑可读文本（敏感值已为 ***），供决策 LLM 参考。"""
    keys = _flatten_profile_keys(profile_masked)
    summary = "可用个人信息键：" + "、".join(keys)
    if len(summary) > max_len:
        summary = summary[:max_len] + "…"
    return summary


async def decide_fill_plan(
    client: BaseLLMClient,
    unfilled_fields: list[dict],
    profile_masked: dict,
) -> list[dict]:
    """决策：未填字段 → [{ref, data_key}] 的填写计划。

    Args:
        unfilled_fields: [{ref, role, name}]，name 为控件标签/当前占位文本
        profile_masked: 脱敏个人信息视图

    Returns:
        非空 plan 返回映射列表；无可填字段/解析失败返回 []（由调用方降级跳过）。
    """
    fields_text = "\n".join(
        f'- ref={f.get("ref", "")} type="{f.get("role", "")}" 标签="{f.get("name") or f.get("type") or ""}"'
        for f in unfilled_fields
    ) or "(无待填字段)"

    user = (
        "以下是待填写的表单控件：\n" + fields_text + "\n\n"
        "请为每个控件选择正确的个人信息键。输出 JSON 数组："
        '[{"ref": "<ref>", "data_key": "<个人信息键>"}, ...]。\n'
        "若某控件在个人信息中没有对应字段，则忽略它不输出。\n"
        f"{_ROLE_HINTS}\n\n{_compact_profile(profile_masked)}"
    )

    raw = await collect_decision(client, user)
    arr = extract_json_array(raw)
    if not arr:
        return []

    plan: list[dict] = []
    seen: set[str] = set()
    for item in arr:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        key = str(item.get("data_key") or "").strip() or str(item.get("key") or "").strip()
        if not ref or not key or ref in seen:
            continue
        seen.add(ref)
        plan.append({"ref": ref, "data_key": key})
    return plan


async def decide_dropdown_plan(
    client: BaseLLMClient,
    dropdowns: list[dict],
    profile_masked: dict,
    skipped_refs: set[str] | None = None,
) -> list[dict]:
    """决策：非标准下拉框 → [{ref, data_key 或 value}]。

    dropdowns 为 probe 结果（由 probe 节点写入 submit_flow）。
    """
    dropdowns_text = "\n".join(
        f'- ref={d.get("ref", "")} label="{d.get("label") or d.get("name") or ""}" '
        f'options=[{"、".join(str(o) for o in (d.get("options") or [])[:12])}]'
        for d in dropdowns
    ) or "- 无下拉框"

    user = (
        "以下是待填写的下拉框（含显示标签与可选值）：\n" + dropdowns_text + "\n\n"
        "输出 JSON 数组：每个元素为 {\"ref\":\"<ref>\", \"data_key\":\"<个人信息键>\"} "
        "或 {\"ref\":\"<ref>\", \"value\":\"<选项文本>\"}，二选一。\n"
        "若下拉框标签/可选值与个人信息匹配，优先用 data_key 引用；无法一一匹配时用字面 value。\n"
        "若不确定则忽略该项。\n"
        f"{_ROLE_HINTS}\n\n{_compact_profile(profile_masked)}"
    )

    raw = await collect_decision(client, user)
    arr = extract_json_array(raw)
    if not arr:
        return []

    skipped = skipped_refs or set()
    plan: list[dict] = []
    seen: set[str] = set()
    for item in arr:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        if not ref or ref in seen or ref in skipped:
            continue
        seen.add(ref)
        entry: dict = {"ref": ref}
        key = str(item.get("data_key") or "").strip()
        value = str(item.get("value") or "").strip()
        if key:
            entry["data_key"] = key
        if value:
            entry["value"] = value
        if "data_key" in entry or "value" in entry:
            plan.append(entry)
    return plan


def profile_keys(profile_masked: dict) -> list[str]:
    """对外暴露：返回拍平的可用 data_key 列表（供调试/测试）。"""
    return _flatten_profile_keys(profile_masked)


def compact_profile(profile_masked: dict) -> str:
    """对外暴露：压缩后的个人信息视图。"""
    return _compact_profile(profile_masked)