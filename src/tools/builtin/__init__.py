"""用户工具函数目录。

在此目录下创建 .py 文件，用 @tool 装饰器定义工具即可被自动发现。

示例 (my_tools.py):

    from pydantic import BaseModel, Field
    from src.tools import tool

    class GetCurrentTimeParams(BaseModel):
        timezone: str = Field(default="Asia/Shanghai", description="时区")

    @tool(name="get_current_time", description="获取指定时区的当前时间")
    async def get_current_time(params: GetCurrentTimeParams) -> str:
        ...
"""

__all__: list[str] = []
