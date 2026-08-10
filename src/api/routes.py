"""API 路由定义。"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from src.api import storage
from src.api.resume_routes import resume_router
from src.api.sse import to_sse
from src.chat.graph import build_graph, ChatState
from src.llm.base import BaseLLMClient
from src.llm.types import Message, TextChunk, ToolResultEvent, ToolCallStartChunk
from src.logger import api_request_done, api_request_error
from src.tools.registry import ToolRegistry

router = APIRouter(prefix="/api")
router.include_router(resume_router)

# LLM 客户端，由 main.py 在启动时注入
_llm_client: BaseLLMClient | None = None
_registry: ToolRegistry | None = None


def set_llm_client(client: BaseLLMClient) -> None:
    """注入 LLM 客户端实例。"""
    global _llm_client
    _llm_client = client


def set_registry(registry: ToolRegistry) -> None:
    """注入工具注册中心。"""
    global _registry
    _registry = registry


def _get_client() -> BaseLLMClient:
    """获取 LLM 客户端，未注入时报错。"""
    if _llm_client is None:
        raise RuntimeError("LLM client 未初始化")
    return _llm_client


def _get_registry() -> ToolRegistry:
    """获取工具注册中心，未注入时报错。"""
    if _registry is None:
        raise RuntimeError("ToolRegistry 未初始化")
    return _registry


def _format_results_as_reminder(results) -> str:
    """将子任务结果列表格式化为 <system-reminder> 标签文本。"""
    from src.sub_agent.types import TaskResult

    lines = [
        "<system-reminder>",
        "以下是你之前派遣的子 agent 执行结果：",
        "",
    ]
    for r in results:
        task_id = r.task.get("id", "?") if isinstance(r.task, dict) else "?"
        if r.success:
            lines.append(f"[任务: {task_id}] 状态: 成功")
            lines.append(f"输出: {r.output}")
        else:
            lines.append(f"[任务: {task_id}] 状态: 失败")
            lines.append(f"错误: {r.error}")
        lines.append("")
    lines.append("</system-reminder>")
    return "\n".join(lines)


class SendMessageBody(BaseModel):
    content: str


@router.get("/conversations")
async def list_conversations():
    """获取所有会话摘要列表。"""
    return storage.list_conversations()


@router.post("/conversations")
async def create_conversation():
    """创建新会话。"""
    return storage.create_conversation()


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """获取指定会话的完整内容。"""
    conv = storage.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, body: SendMessageBody):
    """发送消息并返回 SSE 流式响应。

    使用 LangGraph ReAct 图执行对话，支持工具调用。
    图节点的自定义事件通过 SSE 实时推送给前端。
    """
    conv = storage.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 收集已完成的子任务结果，注入到用户消息
    from src.sub_agent.dispatcher import task_dispatcher
    sub_results = task_dispatcher.drain_results()
    if sub_results:
        reminder = _format_results_as_reminder(sub_results)
        body.content = body.content + "\n\n" + reminder

    # 追加用户消息到存储
    storage.add_message(conversation_id, {"role": "user", "content": body.content})

    # 如果是首条消息，自动更新标题
    is_first = len(conv.get("messages", [])) == 0
    if is_first:
        title = body.content[:30] + ("..." if len(body.content) > 30 else "")
        storage.update_title(conversation_id, title)

    # 构建消息历史
    conv = storage.get_conversation(conversation_id)
    messages = [
        Message(role=m["role"], content=m["content"])
        for m in conv["messages"]
    ]

    client = _get_client()
    registry = _get_registry()
    graph = build_graph(client, registry)

    async def event_generator():
        full_response: list[str] = []
        tool_call_count = 0


        initial_state: ChatState = {
            "messages": messages,
            "response": "",
            "tool_calls": [],
            "loop_count": 0,
        }

        try:
            async for mode, payload in graph.astream(
                initial_state,
                stream_mode=["custom", "values"],
            ):
                if mode == "custom":
                    sse_msg = to_sse(payload)
                    if sse_msg:
                        yield sse_msg

                    if isinstance(payload, TextChunk):
                        full_response.append(payload.delta)
                    elif isinstance(payload, ToolCallStartChunk):
                        tool_call_count += 1

                elif mode == "values":
                    pass

            if full_response:
                storage.add_message(
                    conversation_id,
                    {"role": "assistant", "content": "".join(full_response)},
                )

            api_request_done(conversation_id, len("".join(full_response)), tool_call_count)

        except Exception as exc:
            api_request_error(conversation_id, str(exc))
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """删除指定会话。"""
    storage.delete_conversation(conversation_id)
    return Response(status_code=204)
