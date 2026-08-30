"""LangGraph 对话图。

既有 ReAct 循环（chat_node ↔ tool_node）叠加简历投递的确定性状态机：

    普通对话：  chat_node → [有工具调用?] → tool_node → chat_node ...
                结束
    投递流程：  entry 路由看到 submit_flow 活跃 → 直达对应流程节点，
                由 current_stage 决定从哪一步继续；流程节点链式执行浏览器操作，
                仅在「语义判断」处调用受控 LLM（决策点），不依赖 LLM 编排顺序。

投递流程的进入：普通对话中 LLM 决定调用 browser_navigate 成功后，tool_node
初始化 submit_flow（current_stage=waiting_login）并结束本轮，等待用户回复。
"""

from __future__ import annotations

import json
import time
from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import RunnableConfig
from typing_extensions import NotRequired

from src.chat.submit_flow import (
    flow_fill_dropdowns_node,
    flow_fill_form_node,
    flow_get_personal_node,
    flow_probe_dropdowns_node,
    flow_resume_choice_node,
    flow_snapshot_again_node,
    flow_snapshot_node,
    flow_upload_node,
    is_active_flow,
    new_submit_flow,
)
from src.llm.base import BaseLLMClient
from src.llm.types import (
    Message,
    StreamEvent,
    TextChunk,
    ThinkingChunk,
    ToolCall,
    ToolCallDeltaChunk,
    ToolCallEndChunk,
    ToolCallStartChunk,
    ToolResultEvent,
)
from src.logger import (
    graph_loop,
    llm_request_done,
    llm_request_start,
    tool_call_result,
    tool_call_start,
    tool_exec,
)
from src.prompt.prompt import build_system_prompt
from src.tools.registry import ToolRegistry

# ---- 常量 ----
MAX_TOOL_LOOPS = 10


# ---- 图状态 ----

class ChatState(TypedDict):
    """ReAct 对话图状态。

    每次图执行对应一次用户输入 → 最终回复的完整过程。
    messages 累积全部历史（含 tool 角色消息），
    tool_calls 存放当前轮 LLM 产出的工具调用列表，
    loop_count 追踪 ReAct 循环次数。
    submit_flow 保存投递流程状态（非投递会话不存在）。
    """

    messages: list[Message]
    response: str
    tool_calls: NotRequired[list[ToolCall]]
    loop_count: NotRequired[int]
    submit_flow: NotRequired[dict]


# ---- 节点 ----

async def chat_node(
    state: ChatState,
    config: RunnableConfig,
    *,
    client: BaseLLMClient,
    tool_defs: list[dict],
) -> dict:
    """调用 LLM 获取回复，收集文本和工具调用。

    利用 LangGraph stream_writer 将每个 StreamEvent 实时透传给
    图的上层调用方（API 层的 astream_events 监听器）。

    工具调用的JSON参数以增量方式到达，在此节点中按 tool_id 拼接，
    End 事件后统一json.loads 解析。
    """
    writer = get_stream_writer()
    loop = state.get("loop_count", 0)

    full_text: list[str] = []
    # tool_id → {"name": str, "args_json": str}
    tool_calls_data: dict[str, dict[str, str]] = {}

    rid = llm_request_start(client.model, len(state["messages"]), len(tool_defs))
    try:
        async for event in client.stream(
            state["messages"],
            system=build_system_prompt(),
            tools=tool_defs if tool_defs else None,
        ):
            _dispatch_event(event, writer, full_text, tool_calls_data)
    except Exception:
        llm_request_done(rid, len("".join(full_text)), -1)
        raise

    # 拼接完成后逐条解析
    tool_calls: list[ToolCall] = []
    for tool_id, data in tool_calls_data.items():
        try:
            arguments = json.loads(data["args_json"])
        except json.JSONDecodeError:
            arguments = {}
        tool_calls.append(
            ToolCall(
                tool_id=tool_id,
                tool_name=data["name"],
                arguments=arguments,
            )
        )

    # 构建 assistant 消息
    text_output = "".join(full_text)
    llm_request_done(rid, len(text_output), len(tool_calls))
    for tc in tool_calls:
        tool_call_start(tc.tool_name, tc.tool_id, json.dumps(tc.arguments, ensure_ascii=False))

    assistant_msg = Message(
        role="assistant",
        content=text_output,
        tool_calls=tool_calls if tool_calls else None,
    )

    graph_loop(loop, len(state["messages"]), len(tool_defs), len(text_output), len(tool_calls))

    return {
        "messages": state["messages"] + [assistant_msg],
        "tool_calls": tool_calls,
        "loop_count": loop + 1,
    }


async def tool_node(
    state: ChatState,
    config: RunnableConfig,
    *,
    registry: ToolRegistry,
    conversation_id: str | None = None,
) -> dict:
    """执行工具调用并回传结果。

    遍历 state["tool_calls"]，逐一调用 registry.execute()，每次执行结果：
    1. 通过 writer 实时透传 ToolResultEvent
    2. 以 role="tool" 的 Message 追加到对话历史
    3. 若 browser_navigate 执行成功，初始化投递流程状态（等用户登录）。
    """
    writer = get_stream_writer()

    tool_messages: list[Message] = []
    flow_state: dict | None = None

    for tc in state.get("tool_calls", []):
        t0 = time.perf_counter()
        result = await registry.execute(tc.tool_name, tc.arguments)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        tool_exec(tc.tool_name, tc.tool_id, elapsed_ms, result.is_error)
        tool_call_result(tc.tool_name, tc.tool_id, result.output, result.is_error)

        # 透传执行结果
        writer(ToolResultEvent(
            tool_id=tc.tool_id,
            content=result.output,
            is_error=result.is_error,
        ))

        tool_messages.append(
            Message(
                role="tool",
                content=result.output,
                tool_call_id=tc.tool_id,
            )
        )

        # 投递入口：browser_navigate 成功 → 初始化流程
        if not result.is_error and tc.tool_name == "browser_navigate":
            url = (tc.arguments.get("url") if isinstance(tc.arguments, dict) else "") or ""
            if url:
                flow_state = new_submit_flow(url)

    update: dict = {
        "messages": state["messages"] + tool_messages,
        "tool_calls": [],
        "response": "",
    }
    if flow_state is not None:
        update["submit_flow"] = flow_state
    return update


# ---- 路由 ----

def _should_continue(state: ChatState) -> str:
    """条件路由：有工具调用且未超上限则进入 tool_node，否则结束。"""
    if state.get("tool_calls") and state.get("loop_count", 0) < MAX_TOOL_LOOPS:
        return "tool_node"
    return END


# 投递流程阶段 → 节点名
_FLOW_STAGE_NODE = {
    "waiting_login": "flow_snapshot_form",
    "form_detected": "flow_upload_resume",
    "waiting_resume_choice": "flow_resume_choice",
    "resume_uploaded": "flow_snapshot_again",
    "basic_filled": "flow_probe_dropdowns",
    "dropdowns_probed": "flow_fill_dropdowns",
    "completed": "chat_node",
}


def _entry_route(state: ChatState) -> str:
    """图入口路由：有活跃投递流程 → 去对应流程节点；否则普通对话。"""
    flow = state.get("submit_flow")
    if not is_active_flow(flow):
        return "chat_node"
    stage = flow.get("current_stage")
    node = _FLOW_STAGE_NODE.get(stage, "chat_node")
    return node


def _after_tool(state: ChatState) -> str:
    """工具执行后路由：若刚进入投递流程（等待登录）则结束回合；否则继续 ReAct。"""
    flow = state.get("submit_flow")
    if is_active_flow(flow) and flow.get("current_stage") == "waiting_login":

        return END
    return "chat_node"


def _flow_continue(node: str):
    """构造流程链路的条件路由：流程仍活跃则进入下个节点，否则结束。"""

    def route(state: ChatState) -> str:
        flow = state.get("submit_flow")
        if is_active_flow(flow):
            return node
        url = (flow or {}).get("job_url", "-")
        cur = (flow or {}).get("current_stage", "-")
        return END

    return route


def _after_upload(state: ChatState) -> str:
    """上传简历后：若停在可选则结束；否则跳到再次快照。"""
    flow = state.get("submit_flow")
    if not is_active_flow(flow):
        return END
    if flow.get("current_stage") == "waiting_resume_choice":
        return END
    return "flow_snapshot_again"


def _after_resume_choice(state: ChatState) -> str:
    """选择简历后：若仍有歧义则结束回合，否则继续。"""
    flow = state.get("submit_flow")
    if not is_active_flow(flow):
        return END
    if flow.get("current_stage") == "waiting_resume_choice":

        return END
    return "flow_snapshot_again"


# ---- 图构建 ----

def build_graph(
    client: BaseLLMClient,
    registry: ToolRegistry,
    conversation_id: str | None = None,
) -> StateGraph:
    """构建对话图并编译。

    Args:
        client: LLM 客户端（AnthropicAdapter / OpenAIAdapter）
        registry: 工具注册中心
        conversation_id: 会话 ID（用于投递流程在会话中持久化；当前节点内部不使用）

    Returns:
        编译后的 StateGraph 实例
    """
    tool_defs = registry.list_definitions()

    graph = StateGraph(ChatState)

    # chat_node / tool_node —— 闭包绑定外部业务参数
    async def _chat_node(state: ChatState, config: RunnableConfig) -> dict:
        return await chat_node(state, config, client=client, tool_defs=tool_defs)

    async def _tool_node(state: ChatState, config: RunnableConfig) -> dict:
        return await tool_node(state, config, registry=registry, conversation_id=conversation_id)

    graph.add_node("chat_node", _chat_node)
    graph.add_node("tool_node", _tool_node)

    # 入口：按 submit_flow 阶段路由
    graph.add_conditional_edges(START, _entry_route, {
        "chat_node": "chat_node",
        "flow_snapshot_form": "flow_snapshot_form",
        "flow_upload_resume": "flow_upload_resume",
        "flow_resume_choice": "flow_resume_choice",
        "flow_snapshot_again": "flow_snapshot_again",
        "flow_probe_dropdowns": "flow_probe_dropdowns",
        "flow_fill_dropdowns": "flow_fill_dropdowns",
    })

    # 普通 ReAct
    graph.add_conditional_edges(
        "chat_node",
        _should_continue,
        {"tool_node": "tool_node", END: END},
    )
    graph.add_conditional_edges(
        "tool_node",
        _after_tool,
        {"chat_node": "chat_node", END: END},
    )

    # 投递流程节点
    graph.add_node("flow_snapshot_form", _bind(client, registry, flow_snapshot_node))
    graph.add_node("flow_upload_resume", _bind(client, registry, flow_upload_node))
    graph.add_node("flow_resume_choice", _bind(client, registry, flow_resume_choice_node))
    graph.add_node("flow_snapshot_again", _bind(client, registry, flow_snapshot_again_node))
    graph.add_node("flow_get_personal", _bind(client, registry, flow_get_personal_node))
    graph.add_node("flow_fill_form", _bind(client, registry, flow_fill_form_node))
    graph.add_node("flow_probe_dropdowns", _bind(client, registry, flow_probe_dropdowns_node))
    graph.add_node("flow_fill_dropdowns", _bind(client, registry, flow_fill_dropdowns_node))

    # 流程链路：镜像 _FLOW_STAGE_NODE 的走向
    graph.add_conditional_edges("flow_snapshot_form", _flow_continue("flow_upload_resume"))
    graph.add_conditional_edges("flow_upload_resume", _after_upload)
    graph.add_conditional_edges("flow_resume_choice", _after_resume_choice)
    graph.add_conditional_edges("flow_snapshot_again", _flow_continue("flow_get_personal"))
    graph.add_conditional_edges("flow_get_personal", _flow_continue("flow_fill_form"))
    graph.add_conditional_edges("flow_fill_form", _flow_continue("flow_probe_dropdowns"))
    graph.add_conditional_edges(
        "flow_probe_dropdowns", _flow_continue("flow_fill_dropdowns"),
    )
    graph.add_conditional_edges("flow_fill_dropdowns", _flow_continue(END))

    return graph.compile()


def _bind(client: BaseLLMClient, registry: ToolRegistry, fn):
    """把 client/registry 闭包绑定到流程节点。"""

    async def wrapped(state: ChatState, config: RunnableConfig) -> dict:
        flow = state.get("submit_flow")
        if not is_active_flow(flow):
            # 流程被清理（错误中断）——什么也不做，直接结束
            return {}
        return await fn(state, config, client=client, registry=registry)

    return wrapped


# ---- 内部辅助 ----

def _dispatch_event(
    event: object,
    writer,
    full_text: list[str],
    tool_calls_data: dict[str, dict[str, str]],
) -> None:
    """分发单个 StreamEvent：透传 + 按类型累积。"""
    # 透传给上层
    writer(event)

    if isinstance(event, TextChunk):
        full_text.append(event.delta)

    elif isinstance(event, ThinkingChunk):
        pass  # 思考过程仅透传，不参与最终消息

    elif isinstance(event, ToolCallStartChunk):
        tool_calls_data[event.tool_id] = {
            "name": event.tool_name,
            "args_json": "",
        }

    elif isinstance(event, ToolCallDeltaChunk):
        if event.tool_id in tool_calls_data:
            tool_calls_data[event.tool_id]["args_json"] += event.tool_args_delta

    elif isinstance(event, ToolCallEndChunk):
        pass

    elif isinstance(event, ToolResultEvent):
        pass