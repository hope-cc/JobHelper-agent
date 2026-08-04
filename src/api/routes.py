"""API 路由定义。"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api import storage
from src.llm.base import BaseLLMClient
from src.llm.types import Message, TextChunk

router = APIRouter(prefix="/api")

# LLM 客户端，由 main.py 在启动时注入
_llm_client: BaseLLMClient | None = None


def set_llm_client(client: BaseLLMClient) -> None:
    """注入 LLM 客户端实例。"""
    global _llm_client
    _llm_client = client


def _get_client() -> BaseLLMClient:
    """获取 LLM 客户端，未注入时报错。"""
    if _llm_client is None:
        raise RuntimeError("LLM client 未初始化")
    return _llm_client


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
    """发送消息并返回 SSE 流式响应。"""
    conv = storage.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 追加用户消息到存储
    storage.add_message(conversation_id, {"role": "user", "content": body.content})

    # 如果是首条消息，自动更新标题
    is_first = len(conv.get("messages", [])) == 0
    if is_first:
        title = body.content[:30] + ("..." if len(body.content) > 30 else "")
        storage.update_title(conversation_id, title)

    # 构建消息历史
    conv = storage.get_conversation(conversation_id)
    messages = [Message(role=m["role"], content=m["content"]) for m in conv["messages"]]

    client = _get_client()

    async def event_generator():
        full_response: list[str] = []
        async for event in client.stream(messages):
            if isinstance(event, TextChunk):
                full_response.append(event.delta)
                data = json.dumps({"delta": event.delta}, ensure_ascii=False)
                yield f"event: text\ndata: {data}\n\n"

        # 存储助手回复
        if full_response:
            storage.add_message(conversation_id, {"role": "assistant", "content": "".join(full_response)})

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
