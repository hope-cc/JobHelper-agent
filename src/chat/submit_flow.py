"""简历投递流程的状态机节点。

把 SubmitFlow 从「提示词提醒交给 LLM 临场发挥」改成确定性状态机：
- `current_stage` 控制流程从哪里继续（条件边）；
- 每个节点只做一件事并写回 `submit_flow` 状态字段；
- 浏览器操作结果（表单结构、未填字段、简历、个人信息脱敏视图、下拉框）缓存进状态，
  避免同一 URL 重复 snapshot、同一个人信息重复获取；
- 仅在「语义判断」处调用受控 LLM（决策点：控件→数据键、下拉选项→个人信息值与键）；
- 敏感信息只存脱敏视图，不进 messages 文本。

节点返回 dict 直接更新 ChatState；除节点本身外均为异步函数。所有节点函数签名一致：
``(state, config, *, client, registry)``，由 build_graph 以闭包方式注入 client / registry。
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict
from typing_extensions import NotRequired

from langgraph.config import get_stream_writer
from langgraph.types import RunnableConfig

from src.browser_mcp.fill import has_value, is_fillable, parse_snapshot
from src.browser_mcp.upload import find_upload_control
from src.chat.mapping_functions import decide_dropdown_plan, decide_fill_plan
from src.llm.base import BaseLLMClient
from src.llm.types import Message, TextChunk

# ---- 状态 ----


SubmitFlowStage = Literal[
    "waiting_login",          # 已提示用户登录，等用户回复
    "form_detected",          # 已识别表单结构
    "resume_uploaded",        # 简历已上传（或页面无上传入口已跳过）
    "waiting_resume_choice",  # 多份简历，等用户选
    "basic_filled",           # 基础字段已填
    "dropdowns_probed",       # 下拉框已探测
    "completed",              # 全部完成
]


class SubmitFlowState(TypedDict, total=False):
    job_url: str
    current_stage: SubmitFlowStage
    form_fields: list[dict]
    unfilled_fields: list[dict]
    has_upload_entry: bool
    uploaded_resume: str
    resume_candidates: list[str]
    personal_profile: dict
    dropdowns: list[dict]
    dropdown_fill_plan: list[dict]


def new_submit_flow(job_url: str) -> dict:
    """初始化新的投递流程状态。"""
    return {
        "job_url": job_url,
        "current_stage": "waiting_login",
        "form_fields": [],
        "unfilled_fields": [],
        "has_upload_entry": False,
        "uploaded_resume": "",
        "resume_candidates": [],
        "personal_profile": {},
        "dropdowns": [],
        "dropdown_fill_plan": [],
    }


def is_active_flow(flow: SubmitFlowState | None) -> bool:
    """当前是否有需要继续处理的投递流程。"""
    return bool(flow and flow.get("current_stage") and flow["current_stage"] != "completed")


# ---- 节点 ----


async def flow_snapshot_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """节点：读取表单结构，识别上传入口。

    stage: waiting_login → form_detected
    """
    flow = dict(state.get("submit_flow") or {})
    res = await registry.execute("browser_snapshot", {})
    if res.is_error:
        return _flow_error(state, f"获取表单快照失败：{res.output}")

    elements = parse_snapshot(res.output or "")
    fillable = [e for e in elements if is_fillable(e) and not has_value(e)]
    flow["form_fields"] = [parse_ref(e) for e in elements]
    flow["unfilled_fields"] = [parse_ref(e) for e in fillable]
    flow["has_upload_entry"] = find_upload_control(elements) is not None
    flow["current_stage"] = "form_detected"

    upload_hint = "，包含简历上传入口" if flow["has_upload_entry"] else "，无简历上传入口"
    return _continue(state, flow, f"已识别投递表单（{len(fillable)} 个待填字段{upload_hint}）。")


async def flow_upload_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """节点：上传简历（或跳过）。

    stage: form_detected → resume_uploaded / waiting_resume_choice
    """
    flow = dict(state.get("submit_flow") or {})
    if not flow.get("has_upload_entry"):
        flow["current_stage"] = "resume_uploaded"
        flow["uploaded_resume"] = ""
        return _continue(state, flow, "未检测到简历上传入口，跳过上传步骤。")

    res = await registry.execute("browser_upload_resume", {"ref": "", "resume": ""})
    if res.is_error:
        return _flow_error(state, f"上传简历失败：{res.output}")

    out = res.output or ""
    if "已上传" in out:
        flow["current_stage"] = "resume_uploaded"
        flow["uploaded_resume"] = out
        return _continue(state, flow, out)
    if "请告诉" in out or "请回复" in out or "候选" in out:
        # 多份简历：需要用户选择
        flow["current_stage"] = "waiting_resume_choice"
        flow["resume_candidates"] = _extract_resume_candidates(out)
        return _continue(state, flow, out)
    return _flow_error(state, f"上传简历结果异常：{out}")


async def flow_resume_choice_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """节点：用户已从候选简历中做出选择，按选择上传。

    stage: waiting_resume_choice → resume_uploaded
    """
    flow = dict(state.get("submit_flow") or {})
    user_msgs = [m for m in state.get("messages", []) if m.role == "user"]
    spec = user_msgs[-1].content.strip() if user_msgs else ""

    res = await registry.execute("browser_upload_resume", {"ref": "", "resume": spec})
    if res.is_error:
        return _flow_error(state, f"选择简历失败：{res.output}")
    out = res.output or ""
    if "已上传" in out:
        flow["current_stage"] = "resume_uploaded"
        flow["uploaded_resume"] = out
        return _continue(state, flow, out)
    # 选择仍有歧义：继续留在等待阶段
    flow["resume_candidates"] = _extract_resume_candidates(out)
    return _continue(state, flow, out, keep_stage="waiting_resume_choice")


async def flow_snapshot_again_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """快照：重新识别未填字段（简历解析后可能已自动填写一部分）。"""
    flow = dict(state.get("submit_flow") or {})
    res = await registry.execute("browser_snapshot", {})
    if res.is_error:
        return _flow_error(state, f"再次获取快照失败：{res.output}")

    elements = parse_snapshot(res.output or "")
    fillable = [e for e in elements if is_fillable(e) and not has_value(e)]
    flow["unfilled_fields"] = [parse_ref(e) for e in fillable]
    if not flow.get("current_stage"):
        flow["current_stage"] = "resume_uploaded"
    return _continue(state, flow, f"已更新待填字段：剩余 {len(fillable)} 个输入框。")


async def flow_get_personal_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """获取脱敏个人信息视图（真实值不进状态/messages）。"""
    flow = dict(state.get("submit_flow") or {})
    res = await registry.execute("getPersonalInfo", {})
    if res.is_error:
        return _flow_error(state, f"获取个人信息失败：{res.output}")

    flow["personal_profile"] = _parse_masked_profile(res.output)
    return _continue(state, flow, "已获取个人信息（敏感字段脱敏）。")


async def flow_fill_form_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """决策 + 填写基础字段。

    stage: resume_uploaded → basic_filled
    """
    flow = dict(state.get("submit_flow") or {})
    unfilled = flow.get("unfilled_fields") or []
    profile = flow.get("personal_profile") or {}

    plan = await decide_fill_plan(client, unfilled, profile)
    res = await registry.execute("browser_fill_form", {"items": plan})
    if res.is_error:
        return _flow_error(state, f"填写基础字段失败：{res.output}")

    flow["current_stage"] = "basic_filled"
    flow["unfilled_fields"] = []
    return _continue(state, flow, res.output or "基础字段填写完成。")


async def flow_probe_dropdowns_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """探测非标准下拉框，结构化存入 state.dropdowns。

    stage: basic_filled → dropdowns_probed
    """
    flow = dict(state.get("submit_flow") or {})
    res = await registry.execute("browser_probe_dropdowns", {"refs": []})
    if res.is_error:
        return _flow_error(state, f"探测下拉框失败：{res.output}")

    dropdowns = parse_probe_output(res.output or "")
    flow["dropdowns"] = dropdowns
    flow["current_stage"] = "dropdowns_probed"
    return _continue(state, flow, f"下拉框探测完成：{len(dropdowns)} 个待填下拉框。")


async def flow_fill_dropdowns_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """决策 + 填写下拉框，流程完成。"""
    flow = dict(state.get("submit_flow") or {})
    dropdowns = flow.get("dropdowns") or []
    profile = flow.get("personal_profile") or {}
    plan = await decide_dropdown_plan(client, dropdowns, profile)
    res = await registry.execute("browser_fill_dropdowns", {"items": plan})
    if res.is_error:
        return _flow_error(state, f"填写下拉框失败：{res.output}")

    flow["dropdown_fill_plan"] = plan
    flow["current_stage"] = "completed"
    return _continue(state, flow, "表单填写完成，请在浏览器中确认后提交。")


# ---- 内部辅助 ----


def parse_ref(el: dict) -> dict:
    """把快照元素压缩为「填写计划」使用的字段。"""
    return {
        "ref": el.get("ref", ""),
        "name": el.get("name", ""),
        "role": el.get("role", ""),
    }


def _continue(
    state: dict,
    flow: dict,
    text: str,
    *,
    keep_stage: str | None = None,
) -> dict:
    """更新 state：追加 assistant 消息（流式透传 + 记录），保留流程字段。

    keep_stage 非空时强制指定 current_stage（如留在 waiting 阶段）。
    """
    if keep_stage:
        flow["current_stage"] = keep_stage
    return {
        "messages": _append(state, text),
        "tool_calls": [],
        "response": "",
        "submit_flow": flow,
    }


def _flow_error(state: dict, text: str) -> dict:
    """流程中断：输出错误说明，并清除活跃流程（回到普通对话）。"""
    writer = get_stream_writer()
    writer(TextChunk(delta=text))
    return {
        "messages": list(state.get("messages", [])) + [Message(role="assistant", content=text)],
        "tool_calls": [],
        "response": "",
        "submit_flow": None,
    }


def _append(state: dict, text: str) -> list:
    """把一条回复消息写入 state.messages，并流式透传给前端。"""
    writer = get_stream_writer()
    writer(TextChunk(delta=text))
    return list(state.get("messages", [])) + [Message(role="assistant", content=text)]


def _extract_resume_candidates(text: str) -> list[str]:
    """从多份简历提示文本中提取候选文件名。"""
    names: list[str] = []
    for line in (text or "").splitlines():
        m = re.match(r"^\s*\d+[.、]\s*(\S+\.pdf)", line.strip())
        if m:
            names.append(m.group(1))
    return names


def _parse_masked_profile(json_text: str) -> dict:
    """解析 getPersonalInfo 返回的脱敏 JSON；失败返回 {}。"""
    import json

    try:
        data = json.loads(json_text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def parse_probe_output(text: str) -> list[dict]:
    """把 browser_probe_dropdowns 文本输出解析为结构化列表。

    输出形如：
        - [e1] 学历（未填）：本科、硕士、博士
        - [e2] 籍贯（未填）：识别失败 - xxx
    """
    dropdowns: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        m = re.match(r"^-\s*\[([^\]]+)\]\s*(.+?)（未填）：\s?(.*)$", line)
        if not m:
            continue
        ref, label, opts_txt = m.group(1), m.group(2).strip(), m.group(3).strip()
        if opts_txt.startswith("识别失败"):
            dropdowns.append({"ref": ref, "label": label, "options": [], "failed": opts_txt})
            continue
        options = [o for o in opts_txt.split("、") if o.strip()]
        dropdowns.append({"ref": ref, "label": label, "options": options})
    return dropdowns