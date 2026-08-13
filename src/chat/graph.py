"""LangGraph ReAct 对话图。

在 LangGraph 上实现标准 ReAct 循环：
    chat_node → [有工具调用?] → tool_node → chat_node → ...
                   ↓ (无)
                  END

chat_node 调用 LLM 并传入工具定义，tool_node 执行工具并回传结果。
利用 LangGraph stream_writer 机制实时透传流式事件给上层（API/CLI）。
"""

from __future__ import annotations

import json
import time
from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph
from langgraph.types import RunnableConfig
from typing_extensions import NotRequired

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
from src.logger import graph_loop, llm_request_start, llm_request_done, tool_call_start, tool_call_result, tool_exec
from src.api import storage
from src.prompt.prompt import build_system_prompt, is_submit_flow_tool, next_step_reminder
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
    """

    messages: list[Message]
    response: str
    tool_calls: NotRequired[list[ToolCall]]
    loop_count: NotRequired[int]
    in_submit_flow: NotRequired[bool]


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

    遍历 state["tool_calls"]，逐一调用 registry.execute()，
    每次执行结果：
    1. 通过 writer 实时透传 ToolResultEvent
    2. 以 role="tool" 的 Message 追加到对话历史
    3. 投递流程中，进入流程（出现上传/个人信息等专属工具）后，
       每步完成追加一条「下一步该做什么」的 system_reminder 消息，
       并（若有 conversation_id）持久化到会话存储，阻止 agent 提前停止。
    """
    writer = get_stream_writer()

    tool_messages: list[Message] = []
    in_flow = bool(state.get("in_submit_flow"))

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

        # 工具结果消息
        tool_messages.append(
            Message(
                role="tool",
                content=result.output,
                tool_call_id=tc.tool_id,
            )
        )

        # 投递流程提醒：流程专属工具出现即进入流程；此后每一步都注入下一步提醒
        if is_submit_flow_tool(tc.tool_name):
            in_flow = True
        if in_flow:
            reminder = next_step_reminder(tc.tool_name)
            if reminder:
                tool_messages.append(Message(
                    role="user",
                    content=f"<system-reminder>\n{reminder}\n</system-reminder>",
                ))
                if conversation_id:
                    try:
                        storage.add_system_reminder(conversation_id, reminder)
                    except Exception:
                        # 提醒持久化失败不影响工具执行（仅本次不落库）
                        pass

    return {
        "messages": state["messages"] + tool_messages,
        "tool_calls": [],
        "response": "",
        "in_submit_flow": in_flow,
    }


# ---- 路由 ----

def _should_continue(state: ChatState) -> str:
    """条件路由：有工具调用且未超上限则进入 tool_node，否则结束。"""
    if state.get("tool_calls") and state.get("loop_count", 0) < MAX_TOOL_LOOPS:
        return "tool_node"
    return END


# ---- 图构建 ----

def build_graph(
    client: BaseLLMClient,
    registry: ToolRegistry,
    conversation_id: str | None = None,
) -> StateGraph:
    """构建 ReAct 对话图并编译。

    Args:
        client: LLM 客户端（AnthropicAdapter / OpenAIAdapter）
        registry: 工具注册中心
        conversation_id: 会话 ID，用于把投递流程的下一步提醒持久化到会话存储；None 则不持久化。

    Returns:
        编译后的 StateGraph 实例，可调用 .astream_events() 执行
    """
    tool_defs = registry.list_definitions()

    graph = StateGraph(ChatState)

    # chat_node —— 闭包绑定 client 和 tool_defs，
    # langgraph框架只会传入state和config，client和tool_defs是外部业务参数只能通过包装函数闭包传入
    async def _chat_node(state: ChatState, config: RunnableConfig) -> dict:
        return await chat_node(
            state, config, client=client, tool_defs=tool_defs,
        )

    # tool_node —— 闭包绑定 registry 和 conversation_id
    async def _tool_node(state: ChatState, config: RunnableConfig) -> dict:
        return await tool_node(
            state, config, registry=registry, conversation_id=conversation_id,
        )

    graph.add_node("chat_node", _chat_node)
    graph.add_node("tool_node", _tool_node)

    graph.set_entry_point("chat_node")

    graph.add_conditional_edges(
        "chat_node",
        _should_continue,
        {"tool_node": "tool_node", END: END},
    )
    graph.add_edge("tool_node", "chat_node")

    return graph.compile()


# ---- 内部辅助 ----

def _dispatch_event(
    event: StreamEvent,
    writer,
    full_text: list[str],
    tool_calls_data: dict[str, dict[str, str]],
) -> None:
    """分发单个 StreamEvent：透传 + 按类型累积。

    Args:
        event: LLM 适配器产出的流式事件
        writer: LangGraph stream_writer
        full_text: 文本缓冲区
        tool_calls_data: 工具调用数据缓冲区
    """
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
        pass  # 参数已累积完整，parse 在循环结束后统一进行

    elif isinstance(event, ToolResultEvent):
        pass  # tool_node 产出的结果事件，chat_node 不作处理
