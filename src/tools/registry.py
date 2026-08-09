"""工具注册中心。

提供 ToolRegistry 单例，管理所有已注册工具的生命周期：
自动发现、注册、查找、定义导出和执行。
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

from .decorator import ToolWrapper
from .types import ToolEntry, ToolResult

if TYPE_CHECKING:
    pass


class ToolRegistry:
    """工具注册中心（单例）。

    在应用启动时初始化，自动扫描 src.tools.builtin 包下的所有模块，
    发现并注册被 @tool 装饰的函数。

    Usage::

        registry = ToolRegistry.get_instance()
        registry.discover("src.tools.builtin")
        print(registry.list_definitions())
    """

    _instance: ToolRegistry | None = None

    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}

    # ---- 单例 ----

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        """获取全局唯一的 ToolRegistry 实例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---- 注册 ----

    def register(self, tool: ToolWrapper) -> None:
        """手动注册一个工具。

        Args:
            tool: 被 @tool 装饰器包装后的 ToolWrapper 实例

        Raises:
            ValueError: 若同名工具已注册
        """
        if tool.name in self._tools:
            raise ValueError(
                f"工具 '{tool.name}' 已注册，不能重复注册同名工具"
            )

        self._tools[tool.name] = ToolEntry(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
            param_model=tool.param_model,
            fn=tool.execute,
        )

    def discover(self, package_path: str = "src.tools.builtin") -> None:
        """自动发现并注册指定包下的所有工具。

        递归扫描 package_path 下的所有 Python 模块，通过 import 后用
        dir() 查找 ToolWrapper 实例并自动注册。

        Args:
            package_path: 要扫描的 Python 包路径（如 "src.tools.builtin"）
        """
        try:
            package = importlib.import_module(package_path)
        except ImportError:
            # 包不存在时静默跳过（用户可能还没创建工具）
            return

        # 确保 __path__ 存在（命名空间包可能没有）
        package_paths = getattr(package, "__path__", None)
        if package_paths is None:
            return

        # 递归遍历包下所有模块
        for _, module_name, _ in pkgutil.walk_packages(
            package_paths,
            prefix=package.__name__ + ".",
        ):
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                # 单个模块导入失败时跳过，不影响其他模块
                continue

            # 遍历模块中的所有导出
            for attr_name in dir(module):
                attr = getattr(module, attr_name, None)
                if isinstance(attr, ToolWrapper):
                    # 已存在的工具跳过不报错（discover 可能被多次调用）
                    if attr.name not in self._tools:
                        self.register(attr)

    # ---- 查找 ----

    def get_tool(self, name: str) -> ToolEntry | None:
        """按名称查找工具。"""
        return self._tools.get(name)

    # ---- 定义导出 ----

    def list_definitions(self) -> list[dict]:
        """返回所有工具的 LLM 兼容定义列表。

        每个元素格式：
            {"name": str, "description": str, "input_schema": dict}

        input_schema 为 JSON Schema 格式，可直接传给 Anthropic/OpenAI API。
        """
        return [
            {
                "name": entry.name,
                "description": entry.description,
                "input_schema": entry.parameters,
            }
            for entry in self._tools.values()
        ]

    # ---- 执行 ----

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        """执行指定工具。

        工具不存在或执行异常时均返回 is_error=True 的 ToolResult。

        Args:
            name: 工具名称
            arguments: JSON 参数字典

        Returns:
            ToolResult — output 为结果文本，is_error 标记是否为错误
        """
        entry = self._tools.get(name)
        if entry is None:
            return ToolResult(
                output=f"[工具不存在] 未找到名为 '{name}' 的工具",
                is_error=True,
            )

        return await entry.fn(arguments)
