"""工具装饰器。

提供 @tool 装饰器，将 Pydantic 参数模型 + async 函数封装为
可被注册中心管理的 ToolWrapper 对象。
"""

from __future__ import annotations

import inspect
from typing import Callable, get_type_hints

from pydantic import BaseModel

from .types import ToolResult


class ToolWrapper:
    """装饰后的工具对象。

    封装工具的元信息（名称、描述、参数 schema）和执行逻辑。
    ToolRegistry 通过此类管理所有已注册工具。
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        param_model: type[BaseModel],
        parameters: dict,
        fn: Callable,
    ):
        self.name = name
        self.description = description
        self.param_model = param_model
        self.parameters = parameters
        self._fn = fn

    async def execute(self, arguments: dict) -> ToolResult:
        """接收 JSON 参数字典，校验后调用原函数。

        参数校验失败或函数执行异常时返回 is_error=True 的 ToolResult。
        工具函数可直接返回 str（自动包装为 ToolResult）或返回 ToolResult。

        无论成功或失败，统一返回 ToolResult，LLM 根据 output 内容自行判断。
        """
        try:
            params = self.param_model(**arguments)
        except Exception as exc:
            return ToolResult(
                output=f"[工具执行错误] 参数校验失败: {exc}",
                is_error=True,
            )

        try:
            result = await self._fn(params)
            if isinstance(result, ToolResult):
                return result
            # 向后兼容：工具函数返回 str 时自动包装
            return ToolResult(output=str(result))
        except Exception as exc:
            return ToolResult(
                output=f"[工具执行错误] {exc}",
                is_error=True,
            )


def tool(*, name: str, description: str) -> Callable:
    """将 async 函数注册为可被 LLM 调用的工具。

    Usage::

        from pydantic import BaseModel

        class MyParams(BaseModel):
            query: str

        @tool(name="my_tool", description="示例工具")
        async def my_tool(params: MyParams) -> str:
            return f"结果: {params.query}"

    要求：
    - 被装饰函数必须是 async 函数
    - 第一个参数的类型注解必须是 BaseModel 子类
    - 返回值应为 str（非 str 会被 str() 转换）

    装饰器会自动从 Pydantic 模型提取 JSON Schema 作为工具的参数定义。
    """

    def decorator(fn: Callable) -> ToolWrapper:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(
                f"@tool 装饰的函数必须是 async 函数，"
                f"但 {fn .__name__} 不是 async 函数"
            )

        hints = get_type_hints(fn)
        # 第一个参数是 params，跳过 return 键
        param_types = [
            (p_name, p_type)
            for p_name, p_type in hints.items()
            if p_name != "return"
        ]

        if not param_types:
            raise TypeError(
                f"@tool 装饰的函数 {fn.__name__} 必须有至少一个参数，"
                f"且第一个参数的类型注解为 BaseModel 子类"
            )

        first_name, first_type = param_types[0]

        if not (isinstance(first_type, type) and issubclass(first_type, BaseModel)):
            raise TypeError(
                f"@tool 装饰的函数 {fn.__name__} 的第一个参数 "
                f"'{first_name}' 必须是 BaseModel 子类，实际为 {first_type}"
            )

        # 从 Pydantic 模型提取 JSON Schema
        raw_schema = first_type.model_json_schema()

        # 清理不兼容字段：Anthropic 和 OpenAI 都不接受 title / additionalProperties
        raw_schema.pop("title", None)
        raw_schema.pop("additionalProperties", None)

        # 递归清理嵌套属性中的 title
        _strip_titles(raw_schema)

        return ToolWrapper(
            name=name,
            description=description,
            param_model=first_type,
            parameters=raw_schema,
            fn=fn,
        )

    return decorator


def _strip_titles(schema: dict) -> None:
    """递归移除 schema 中所有嵌套层级的 title 字段。"""
    if not isinstance(schema, dict):
        return
    schema.pop("title", None)
    for value in schema.values():
        if isinstance(value, dict):
            _strip_titles(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _strip_titles(item)
