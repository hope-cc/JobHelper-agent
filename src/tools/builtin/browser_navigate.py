"""browser_navigate 工具：以有头方式在 Playwright MCP 浏览器中打开投递页。"""

from urllib.parse import urlparse

from pydantic import BaseModel, Field

from src.browser_mcp.client import call_tool
from src.tools import ToolResult, tool


class Params(BaseModel):
    url: str = Field(..., description="简历投递页 URL，需包含协议头（如 https://）")


@tool(
    name="browser_navigate",
    description=(
        "以有头方式在 Playwright MCP 浏览器中打开简历投递页 URL，并等待用户登录。"
        "首次投递时调用本工具打开投递页；打开成功后提示用户登录并切换到表单页（保持浏览器只有一个页面），"
        "完成后用户回复「继续」。"
    ),
)
async def browser_navigate(params: Params):
    url = (params.url or "").strip()
    if not url:
        return ToolResult(output="URL 不能为空", is_error=True)

    parsed = urlparse(url)
    if not parsed.scheme:
        return ToolResult(
            output=f"URL 格式不正确，必须包含协议头（如 http:// 或 https://）：{url}",
            is_error=True,
        )
    if parsed.scheme not in ("http", "https", "data", "about"):
        return ToolResult(
            output=f"不支持的 URL 协议 {parsed.scheme}：{url}",
            is_error=True,
        )

    text, err = await call_tool("browser_navigate", {"url": url})
    if err:
        return ToolResult(output=text, is_error=True)

    return ToolResult(
        output=(
            f"{text}\n\n页面已打开。请在浏览器中完成登录并切换到简历投递表单页"
            "（保持浏览器只有一个页面），完成后回复「继续」。"
        )
    )
