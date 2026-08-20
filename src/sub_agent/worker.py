"""子 agent 执行器（sub_agent_executor）。

每个子 agent 运行一个轻量 ReAct 循环：
    LLM 推理（带工具）→ 执行工具 → 回传结果 → 重复 → 输出

不依赖 LangGraph——仅用几十行循环逻辑，每条任务独立执行。
"""

from __future__ import annotations

import json

from src.llm.base import BaseLLMClient
from src.llm.types import (
    Message,
    TextChunk,
    ToolCall,
    ToolCallDeltaChunk,
    ToolCallStartChunk,
)
from src.tools.registry import ToolRegistry

from .types import TaskResult

# 子 agent 最多执行几轮 ReAct
MAX_SUB_AGENT_LOOPS = 5


# ---- Prompt 构建 ----

def _build_system_prompt(task: dict) -> str:
    """根据任务字段构建招聘信息提取的系统提示词。"""
    return f"""你是一个精通提取招聘信息的子agent，请根据任务要求执行操作。

【任务要求】: {task.get('context', '')}

【任务步骤】：调用工具 {task.get('action', 'click')}，传入参数 url="{task.get('url', '')}" 和 text="{task.get('target_text', '')}" 来抓取该公司的招聘简章并提取所有招聘职位，并按照“一个职位对应一个 JSON 对象”的方式输出。

【字段定义】：每个职位必须包含以下字段：
{
    "公司": "",
    "职位": "",
    "工作职责": "",
    "任职要求": "",
    "工作地点": "",
    "投递方式": ""
}

【注意】：
1、请严格按照上述json格式输出，不要添加额外的解释或文本。
2、招聘信息没有提供某些字段时，该字段的值应为空字符串。
3、请确保输出的json格式正确，避免语法错误。
4、职位、工作职责、任职要求用招聘网页的原句不要修改；
5、投递方式应该简略描述，仅包括投递方式和投递网址，尽量简短；

【输出格式】：
[
    {
        "公司": "招商银行·招银网络科技",
        "职位": "后端开发工程师",
        "工作职责": "招聘网页中的原文",
        "任职要求": "招聘网页中的原文",
        "工作地点": "广州/深圳",
        "投递方式": "官网投递：https://cmbnt.cmbchina.com"
    }
]
"""


# ---- 流式响应收集 ----

async def _collect_llm_response(
    client: BaseLLMClient,
    messages: list[Message],
    system_prompt: str,
    tool_defs: list[dict],
) -> tuple[str, list[ToolCall]]:
    """调用 LLM 流式接口，收集完整文本和工具调用。

    遍历 client.stream() 产出的 StreamEvent，
    按类型分别累积到文本缓冲区和工具调用缓冲区。
    流结束后解析工具调用的 JSON 参数。

    Returns:
        (text_output, tool_calls)
    """
    full_text: list[str] = []
    tool_calls_data: dict[str, dict[str, str]] = {}

    async for event in client.stream(
        messages,
        system=system_prompt,
        tools=tool_defs if tool_defs else None,
    ):
        if isinstance(event, TextChunk):
            full_text.append(event.delta)

        elif isinstance(event, ToolCallStartChunk):
            tool_calls_data[event.tool_id] = {
                "name": event.tool_name,
                "args_json": "",
            }

        elif isinstance(event, ToolCallDeltaChunk):
            if event.tool_id in tool_calls_data:
                tool_calls_data[event.tool_id]["args_json"] += event.tool_args_delta

    # 解析工具调用参数
    tool_calls: list[ToolCall] = []
    for tool_id, data in tool_calls_data.items():
        try:
            arguments = json.loads(data["args_json"])
        except json.JSONDecodeError:
            arguments = {}
        tool_calls.append(ToolCall(
            tool_id=tool_id,
            tool_name=data["name"],
            arguments=arguments,
        ))

    return "".join(full_text), tool_calls


# ---- 主入口 ----

async def sub_agent_executor(task: dict, client: BaseLLMClient) -> TaskResult:
    """子 agent 执行入口——轻量 ReAct 循环。

    调度器在分配空闲客户端后调用此函数，完成一条子任务的
    完整推理→执行→输出流程。

    Args:
        task: 任务字典（id, action, url, target_text, context）
        client: 调度器分配的空闲 LLM 客户端

    Returns:
        TaskResult，output 为 LLM 最终文本（JSON），success=True
        表示成功完成
    """
    registry = ToolRegistry.get_instance()
    tool_defs = registry.list_definitions()
    system_prompt = _build_system_prompt(task)

    user_content = f"请执行任务：{task.get('context', '')}"
    messages: list[Message] = [
        Message(role="user", content=user_content)
    ]

    for _loop in range(MAX_SUB_AGENT_LOOPS):
        # 1. 调用 LLM
        try:
            text_output, tool_calls = await _collect_llm_response(
                client, messages, system_prompt, tool_defs,
            )
        except Exception as exc:
            print(f"LLM 调用失败: {exc}")
            return TaskResult(
                task=task,
                output="",
                success=False,
                error=f"LLM 调用失败: {exc}",
            )

        # 2. 追加 assistant 消息
        messages.append(Message(
            role="assistant",
            content=text_output,
            tool_calls=tool_calls if tool_calls else None,
        ))

        # 3. 无工具调用 → 结束，返回最终文本
        if not tool_calls:
            import time
            print(time.time(), f"任务完成")
            return TaskResult(
                task=task,
                output=text_output,
                success=True,
            )

        # 4. 执行工具，追加 tool 消息
        for tc in tool_calls:
            result = await registry.execute(tc.tool_name, tc.arguments)
            messages.append(Message(
                role="tool",
                content=result.output,
                tool_call_id=tc.tool_id,
            ))

    # 超出最大轮数
    print(f"超过最大工具调用轮数 ({MAX_SUB_AGENT_LOOPS})")
    return TaskResult(
        task=task,
        output="",
        success=False,
        error=f"超过最大工具调用轮数 ({MAX_SUB_AGENT_LOOPS})",
    )



