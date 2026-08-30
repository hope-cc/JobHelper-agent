"""简历投递流程的状态机节点。

把 SubmitFlow 从「提示词提醒交给 LLM 临场发挥」改成确定性状态机：
- `current_stage` 控制流程从哪里继续（条件边）；
- 每个节点只做一件事并写回 `submit_flow` 状态字段；
- 浏览器操作结果缓存进状态（避免同一 URL 重复 snapshot、同一个人信息重复获取）：
  快照解析产出三类 `{字段名: ref}` 字典（`textbox_fields` / `dropdown_fields` / `upload_fields`），
  以及完整/未填字段表；
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

from src.browser_mcp.fill_form import browser_fill_form
from src.browser_mcp.fill_dropdowns import browser_fill_dropdowns
from src.browser_mcp.probe_dropdowns import browser_probe_dropdowns
from src.browser_mcp.snapshot import process_browser_snapshot
from src.browser_mcp.upload import browser_upload_resume

from src.chat.mapping_functions import (
    decide_dropdown_plan,
    decide_fill_plan,
)
from src.llm.base import BaseLLMClient
from src.llm.types import Message, TextChunk
from src.logger import logger_info
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
    # 三类字段的 {字段名: ref} 索引（来自 flow_snapshot_node 的快照解析）
    textbox_fields: dict[str, str]
    dropdown_fields: dict[str, str]
    upload_fields: dict[str, str]
    has_upload_entry: bool
    uploaded_resume: str
    resume_candidates: list[str]
    personal_profile: dict
    masked_labels: list[str]  # 脱敏字段的前端标签列表（personal_profile 中键值相等的标记）
    dropdown_options: dict[str, list[str]]  # {字段名: [选项]}，探测结果
    dropdown_fill_plan: list[dict]


def new_submit_flow(job_url: str) -> dict:
    """初始化新的投递流程状态。"""
    return {
        "job_url": job_url,
        "current_stage": "waiting_login",
        "form_fields": [],
        "unfilled_fields": [],
        "textbox_fields": {},
        "dropdown_fields": {},
        "upload_fields": {},
        "has_upload_entry": False,
        "uploaded_resume": "",
        "resume_candidates": [],
        "personal_profile": {},
        "masked_labels": [],
        "dropdown_options": {},
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
    """节点：读取 DOM 树，解析三类字段字典（填空 / 下拉框 / 简历上传）。

    stage: waiting_login → form_detected
    """
    flow = dict(state.get("submit_flow") or {})
    
    url = flow.get("job_url", "-")
    stage = flow.get("current_stage", "-")

    text_box, dropdown, upload = await process_browser_snapshot()
    flow["textbox_fields"] = text_box
    flow["dropdown_fields"] = dropdown
    flow["upload_fields"] = upload


    upload_hint = f"，{len(upload)} 个简历上传入口" if upload else "，无简历上传入口"
    logger_info("flow_snapshot_node", f"已识别投递表单：{len(text_box)} 个填空框、{len(dropdown)} 个下拉框{upload_hint}。")

    return _continue(
        state,
        flow,
        f"已识别投递表单：{len(text_box)} 个填空框、{len(dropdown)} 个下拉框{upload_hint}。",
    )


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
    url = flow.get("job_url", "-")
    stage = flow.get("current_stage", "-")
    upload = flow.get("upload_fields") or {}
    if not upload:
        flow["current_stage"] = "resume_uploaded"
        flow["uploaded_resume"] = ""
        
        return _continue(state, flow, "未检测到简历上传入口，跳过上传步骤。", stage_from=stage)

    ref = list(upload.values())[0]
    res = await browser_upload_resume(ref, "")

    logger_info("flow_upload_node", f"简历上传")


    if res.is_error:
        return _flow_error(state, f"上传简历失败：{res.output}")

    out = res.output or ""
    if "已上传" in out:
        flow["current_stage"] = "resume_uploaded"
        flow["uploaded_resume"] = out
        return _continue(state, flow, out, stage_from=stage)
    if "请告诉" in out or "请回复" in out or "候选" in out:
        # 多份简历：需要用户选择
        flow["current_stage"] = "waiting_resume_choice"
        flow["resume_candidates"] = _extract_resume_candidates(out)
        return _continue(state, flow, out, stage_from=stage)
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
    url = flow.get("job_url", "-")
    stage = flow.get("current_stage", "-")
    user_msgs = [m for m in state.get("messages", []) if m.role == "user"]
    spec = user_msgs[-1].content.strip() if user_msgs else ""

    upload = flow.get("upload_fields") or {}
    ref = list(upload.values())[0]
    res = await browser_upload_resume(ref, spec)
    

    if res.is_error:
        return _flow_error(state, f"选择简历失败：{res.output}")
    out = res.output or ""
    if "已上传" in out:
        flow["current_stage"] = "resume_uploaded"
        flow["uploaded_resume"] = out
        return _continue(state, flow, out, stage_from=stage)
    # 选择仍有歧义：继续留在等待阶段
    flow["resume_candidates"] = _extract_resume_candidates(out)
    return _continue(state, flow, out, keep_stage="waiting_resume_choice", stage_from=stage)


async def flow_snapshot_again_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """快照：重新识别未填字段与三类字段字典（简历解析后可能已自动填写一部分）。"""
    flow = dict(state.get("submit_flow") or {})
    url = flow.get("job_url", "-")
    stage = flow.get("current_stage", "-")

    text_box, dropdown, upload = await process_browser_snapshot()
    flow["textbox_fields"] = text_box
    flow["dropdown_fields"] = dropdown
    flow["upload_fields"] = upload
    
    logger_info("flow_snapshot_again_node", f"已识别投递表单：{len(text_box)} 个填空框、{len(dropdown)} 个下拉框、{len(upload)} 个上传框。")

    return _continue(
            state,
            flow,
            f"上传简历后，已识别投递表单：{len(text_box)} 个填空框、{len(dropdown)} 个下拉框。",
            stage_from=stage,
        )


async def flow_get_personal_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """把个人信息 basic_info 打平成 {前端字段标签: 真实值} 存进 personal_profile。

    只保留 basic_info（含自定义字段），education/award 等列表不进本视图。
    脱敏字段也存真实值；`masked_labels` 记录脱敏字段的标签列表，给 LLM 的
    文本视图里显示为「标签:标签」，后台写表时识别该标记再读出真实值。
    """
    flow = dict(state.get("submit_flow") or {})
    url = flow.get("job_url", "-")
    stage = flow.get("current_stage", "-")

    from src.api import profile_storage
    data = profile_storage.load()
    if data is None:
        return _flow_error(state, "尚未保存个人信息，请先在「个人信息管理」页面填写并保存后再调用。")

    schema = data.get("basic_fields_schema") or []
    label_map = {
        item.get("key"): item.get("label")
        for item in schema
        if isinstance(item, dict) and item.get("key")
    }

    basic = data.get("basic_info") or {}
    personal_profile: dict = {}
    for key, value in basic.items():
        if not value and value != 0:
            continue
        label = label_map.get(key, key)
        personal_profile[label] = value

    mask_keys = data.get("masked_basic_fields") or []
    masked_labels = [label_map.get(k, k) for k in mask_keys]

    flow["personal_profile"] = personal_profile
    flow["masked_labels"] = masked_labels
    logger_info("flow_get_personal_node", f"已获取个人信息（敏感字段脱敏）{personal_profile}")

    return _continue(state, flow, "已获取个人信息（敏感字段脱敏）。", stage_from=stage)


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
    url = flow.get("job_url", "-")
    stage = flow.get("current_stage", "-")
    text_box = flow.get("textbox_fields") or {}
    profile = flow.get("personal_profile") or {}
    masked_labels = flow.get("masked_labels") or []

    plan = await decide_fill_plan(client, text_box, profile, masked_labels)
    logger_info("flow_fill_form_node", f"传入填空字段{text_box}\n，大模型决策：{plan}")

    # plan: {字段名: 值}；按字段名从 textbox_fields 取 ref，脱敏标记回读真实值
    items: list[dict] = []
    for field, value in plan.items():
        ref = text_box.get(field)
        if not ref:
            continue
        masked = value in masked_labels
        if masked:
            value = profile.get(value)
        if value is None or value == "":
            continue
        items.append({"ref": ref, "value": value, "display": "***" if masked else value})

    res = await browser_fill_form(items)

    if res.is_error:
        return _flow_error(state, f"填写基础字段失败：{res.output}")

    # 回写未填字段：plan 覆盖的字段名从 textbox_fields 中移除，其余留在待填
    planned_fields = set(plan)
    flow["textbox_fields"] = {
        name: ref for name, ref in text_box.items() if name not in planned_fields
    }
    flow["current_stage"] = "basic_filled"
    return _continue(state, flow, res.output or "基础字段填写完成。", stage_from=stage)


async def flow_probe_dropdowns_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """探测非标准下拉框：逐个展开，把 {字段名: [选项]} 存入 state.dropdown_options。

    stage: basic_filled → dropdowns_probed
    """
    flow = dict(state.get("submit_flow") or {})
    url = flow.get("job_url", "-")
    stage = flow.get("current_stage", "-")
    fields = flow.get("dropdown_fields") or {}
    options_map = await browser_probe_dropdowns(fields)
    got = {name: opts for name, opts in options_map.items() if opts}
   
    flow["dropdown_options"] = options_map
    flow["current_stage"] = "dropdowns_probed"
    logger_info("flow_probe_dropdowns_node", f"下拉框探测{flow["dropdown_options"]}。")

    return _continue(
        state, flow,
        f"下拉框探测完成：{len(got)} 个下拉框已获取选项（共 {len(fields)} 个）。" if fields else "无待填下拉框。",
        stage_from=stage,
    )


async def flow_fill_dropdowns_node(
    state: dict,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    registry,
) -> dict:
    """决策 + 填写下拉框，流程完成。

    stage: dropdowns_probed → completed
    """
    flow = dict(state.get("submit_flow") or {})
    url = flow.get("job_url", "-")
    stage = flow.get("current_stage", "-")
    dropdown_options = flow.get("dropdown_options") or {}  # {字段名: [选项]}
    dropdown_fields = flow.get("dropdown_fields") or {}    # {字段名: ref}
    profile = flow.get("personal_profile") or {}
    masked_labels = flow.get("masked_labels") or []

    plan = await decide_dropdown_plan(client, dropdown_options, profile, masked_labels)
    logger_info("flow_fill_dropdowns_node", f"下拉框填写计划：{plan}。")

    # plan: {字段名: 值}；按字段名从 dropdown_fields 取 ref，脱敏标记回读真实值
    items: list[dict] = []
    for name, value in plan.items():
        if name not in dropdown_fields:
            continue
        masked = value in masked_labels
        if masked:
            value = profile.get(value)
        if value is None or value == "":
            continue
        items.append({"name": name, "value": value, "display": "***" if masked else value})

    res = await browser_fill_dropdowns(items, dropdown_fields)

    if res.is_error:
        return _flow_error(state, f"填写下拉框失败：{res.output}")

    # 回写未填下拉框：plan 之外的字段（LLM 未找到对应个人信息/未匹配）留在 dropdown_fields
    planned_names = set(plan)
    flow["dropdown_fields"] = {
        name: ref for name, ref in dropdown_fields.items() if name not in planned_names
    }
    flow["dropdown_fill_plan"] = plan
    flow["current_stage"] = "completed"
    return _continue(state, flow, "表单填写完成，请在浏览器中确认后提交。", stage_from=stage)


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
    stage_from: str | None = None,
) -> dict:
    """更新 state：追加 assistant 消息（流式透传 + 记录），保留流程字段。

    keep_stage 非空时强制指定 current_stage（如留在 waiting 阶段）。
    stage_from 为节点进入时的原始 stage（用于记录状态 读→写 变化）。
    """
    old_stage = stage_from or flow.get("current_stage", "-")
    if keep_stage:
        flow["current_stage"] = keep_stage
    new_stage = flow.get("current_stage", "-")
    url = flow.get("job_url", "-")
    
    return {
        "messages": _append(state, text),
        "tool_calls": [],
        "response": "",
        "submit_flow": flow,
    }


def _flow_error(state: dict, text: str) -> dict:
    """流程中断：输出错误说明，并清除活跃流程（回到普通对话）。"""
    flow = state.get("submit_flow") or {}
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


