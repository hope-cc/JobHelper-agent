"""searchJobs 工具。

RAG 查询工具：主 agent 传入用户问题，在已抓取的招聘信息向量库中
做 BM25 + 向量混合检索，RRF 融合排序后返回相关职位。
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from src.rag.store import job_vector_store
from src.tools import tool, ToolResult


class SearchJobsParams(BaseModel):
    """searchJobs 工具的参数。"""

    query: str = Field(
        ...,
        description="用户想查找的职位相关问题或关键词，如「有哪些后端开发岗」「招银网络的 Java 岗位要求是什么」。",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="返回结果条数上限，默认 5，最大 20。",
    )


@tool(
    name="searchJobs",
    description=(
        "在已抓取的招聘信息库中检索与问题相关的职位。"
        "适用于用户询问此前已收集的岗位信息（某公司/某类职位的岗位要求、"
        "任职要求、工作地点、投递方式等）时使用。"
        "返回按相关度排序的职位 JSON 列表。"
    ),
)
async def searchJobs(params: SearchJobsParams) -> str:
    try:
        results = job_vector_store.search(params.query, params.top_k)
    except Exception as exc:
        return ToolResult(
            output=f"[检索失败] 向量库检索异常: {exc}",
            is_error=True,
        )

    if not results:
        return ToolResult(
            output=(
                "未检索到相关职位。可能原因：向量库中还没有抓取到的职位记录，"
                "或没有与问题相关的职位。"
            ),
            is_error=False,
        )

    return json.dumps(results, ensure_ascii=False, indent=2)
