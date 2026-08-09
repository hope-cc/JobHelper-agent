"""JobHelper 工具系统。

提供统一的工具注册、发现和执行机制。

核心组件：
- tool: @tool 装饰器，将 Pydantic 模型 + async 函数封装为工具
- ToolRegistry: 工具注册中心单例，管理工具生命周期
- ToolEntry: 注册中心中的工具条目数据结构

Usage::

    from src.tools import tool, ToolRegistry

    @tool(name="my_tool", description="我的工具")
    async def my_tool(params: MyParams) -> str:
        ...

    registry = ToolRegistry.get_instance()
    registry.register(my_tool)
"""

from .decorator import tool
from .registry import ToolRegistry
from .types import ToolEntry, ToolResult

__all__ = ["tool", "ToolRegistry", "ToolEntry", "ToolResult"]
