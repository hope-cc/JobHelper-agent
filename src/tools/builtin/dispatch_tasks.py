"""dispatch_tasks 工具。

将 TaskDispatcher 暴露为 LLM 可调用的工具。主 agent 调用此工具
传入任务列表，调度器为每个任务 spawn 协程，协程自动从客户端池
获取空闲 LLM 客户端并发执行。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.sub_agent.dispatcher import task_dispatcher
from src.tools import tool


# ---- 参数模型 ----

class TaskItem(BaseModel):
    """单条子 agent 任务。

    描述子 agent 需要执行的一项具体操作。字段由主 agent 在分析
    招聘网站结构后填充，子 agent 根据字段决定调用哪些工具。
    """

    id: str = Field(
        ...,
        description="任务唯一标识，用于结果关联。通常为公司名。",
    )
    action: str = Field(
        default="click",
        description="要执行的操作类型：click（点击后抓取）。",
    )
    url: str = Field(
        ...,
        description="click动作的参数：子agent在该目标网页URL下执行任务。",
    )
    target_text: str | None = Field(
        default=None,
        description="click动作的参数：页面中要点击的文本。",
    )
    context: str | None = Field(
        default=None,
        description="额外的上下文提示，帮助子 agent 理解任务意图。如'调用click工具，传入参数url和target_text来抓取该公司的招聘简章'。",
    )

    class Config:
        extra = "allow"  # 允许调用方传递额外字段，保持扩展性


class DispatchTasksParams(BaseModel):
    """dispatch_tasks 工具的参数。"""

    tasks: list[TaskItem] = Field(
        default_factory=list,
        description="任务列表，每个元素是一个 TaskItem 对象。会追加到调度器的共享队列中。",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "tasks": [
                    {
                        "id": "阿里巴巴",
                        "action": "click",
                        "url": "https://example.com/jobs",
                        "target_text": "阿里巴巴",
                        "context": "调用click工具，传入参数url和target_text来抓取阿里巴巴的招聘简章",
                    },
                    {
                        "id": "腾讯",
                        "action": "click",
                        "url": "https://example.com/jobs",
                        "target_text": "腾讯",
                        "context": "调用click工具，传入参数url和target_text来抓取腾讯的招聘简章",
                    },
                    {
                        "id": "字节跳动",
                        "action": "click",
                        "url": "https://example.com/jobs",
                        "target_text": "字节跳动",
                        "context": "调用click工具，传入参数url和target_text来抓取字节跳动的招聘简章",
                    },
                ],
            }
        }


# ---- 工具定义 ----

@tool(
    name="dispatchTasks",
    description=(
        "向调度器追加批量任务，由多个子 agent 并行处理。"
        "可多次调用，每次调用为任务 spawn 独立协程，"
        "协程自动竞争空闲客户端执行，客户端全忙时挂起等待。"
        "适用于主 agent 分析出若干条待处理的列表项（如公司列表、职位列表），"
        "需要并行抓取每条详情时使用。"
        "调用后立即返回，子 agent 在后台执行，完成后通过回调通知。"
    ),
)
async def dispatchTasks(params: DispatchTasksParams) -> str:
    """向调度器追加批量任务。
    
    为每个任务 spawn 协程，协程自动从客户端池获取空闲客户端执行。
    调用后立即返回摘要字符串，不等待任务完成。
    """
    if not params.tasks:
        return "任务列表为空，未追加任务。"

    return await task_dispatcher.dispatch([t.model_dump() for t in params.tasks])
