"""工具系统共享类型定义。"""

from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel


@dataclass
class ToolResult:
    """工具函数的标准返回值。

    工具函数可以直接 return str（向后兼容）或 return ToolResult。
    使用 ToolResult 时可以精确控制 is_error 状态。

    Usage::

        # 正常返回
        return ToolResult(output="找到 42 个职位")

        # 业务错误（前端展示红色叉号，LLM 收到原样消息）
        return ToolResult(output="搜索关键词太短", is_error=True)
    """

    output: str
    """工具执行后的文本输出，直接作为 LLM 的历史消息。"""

    is_error: bool = False
    """是否为错误结果。前端据此决定展示样式（绿色对勾 / 红色叉号）。"""


@dataclass
class ToolEntry:
    """注册中心中的工具条目。

    每个被 @tool 装饰的工具函数在注册时都会生成一条 ToolEntry，
    由 ToolRegistry 统一管理。
    """

    name: str
    """工具唯一名称，同时用作 LLM 传入的工具标识。"""

    description: str
    """工具描述文本，LLM 据此判断何时调用该工具。"""

    parameters: dict
    """JSON Schema 格式的参数定义，从 Pydantic 模型自动提取。

    示例：
        {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词"},
                "city": {"type": "string", "description": "城市名称"}
            },
            "required": ["keyword", "city"]
        }
    """

    param_model: type[BaseModel]
    """Pydantic 参数模型类，用于校验参数和实例化。"""

    fn: Callable
    """原始 async 可调用对象，执行时传入 param_model 实例，返回 ToolResult。"""
