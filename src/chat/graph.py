"""LangGraph 对话图。

构建最简 state graph，为后续 agent 功能迭代预留扩展点。
"""

from typing import TypedDict

from langgraph.graph import StateGraph

from src.llm.base import BaseLLMClient
from src.llm.types import Message, TextChunk


class ChatState(TypedDict):
    """对话状态。

    messages 累积全量对话历史，response 存放本轮完整回复。
    """

    messages: list[Message]
    response: str


async def chat_node(state: ChatState, *, client: BaseLLMClient) -> dict:
    """对话节点：调用 LLM 客户端，收集完整回复。"""
    full_response: list[str] = []

    async for event in client.stream(state["messages"]):
        if isinstance(event, TextChunk):
            full_response.append(event.delta)

    return {"response": "".join(full_response)}


def build_graph(client: BaseLLMClient) -> StateGraph:
    """构建单节点对话图。"""
    graph = StateGraph(ChatState)

    async def _chat_node(state: ChatState) -> dict:
        return await chat_node(state, client=client)

    graph.add_node("chat", _chat_node)
    graph.set_entry_point("chat")
    graph.set_finish_point("chat")

    return graph
