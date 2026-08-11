"""submitApplication 工具。

填写并提交简历投递表单。首次调用以有头方式打开浏览器并提示用户登录；
之后用户回复「继续」「已提交」时再次调用以推进流程。

工具壳为薄壳：URL 校验与状态机推进逻辑均交给 BrowserManager，
这里只负责读取当前会话ID、调用管理器并包装返回结果。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.browser.context import get_current_conversation
from src.browser.manager import BrowserManager
from src.tools import tool, ToolResult


class Params(BaseModel):
    url: str = Field(default="", description="投递页URL，首次调用必填")
    action: str = Field(
        default="continue",
        description="continue=继续推进, cancel=取消投递",
    )


@tool(
    name="submitApplication",
    description=(
        "填写并提交简历投递表单。首次调用传入投递页URL，以有头方式打开浏览器并提示用户登录；"
        "之后用户回复「继续」「已提交」时再次调用本工具推进流程（无需重复传URL），"
        "工具会根据当前进度自动检测表单、按个人信息填写、检测投递成功。"
        "若登录后进入岗位列表页而非表单页，提示用户手动点击目标岗位进入投递页面"
        "（当前标签页或新标签页均可），本工具会自动扫描浏览器中所有标签页识别表单。"
        "用户要取消时传 action='cancel'。"
    ),
)
async def submitApplication(params: Params) -> ToolResult:
    conversation_id = get_current_conversation()
    if not conversation_id:
        return ToolResult(
            output="[submitApplication] 未获取到当前会话ID，本工具只能在对话中调用。",
            is_error=True,
        )

    result = await BrowserManager.get_instance().submit(
        conversation_id, params.url.strip(), params.action
    )
    # 管理器返回以 "[submitApplication]" 前缀开头的文本表示错误
    return ToolResult(output=result, is_error=result.startswith("[submitApplication]"))
