from pydantic import BaseModel, Field
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from playwright.async_api import (
    async_playwright,
    TimeoutError,
    Error 
)
from urllib.parse import urlparse

from src.tools import tool, ToolResult

class Params(BaseModel):
    url: str = Field(default="", description="网页的url链接")


@tool(name="getTextFromURL", description="根据url获取网页文本内容")
async def getTextFromURL(params: Params) -> str:
    # 1. 基础空值校验
    if not params.url:
        return ToolResult(output="URL 不能为空", is_error=True)

    # 2. URL 格式规范校验
    parsed_url = urlparse(params.url)
    if not parsed_url.scheme or not parsed_url.netloc:
        return ToolResult(output=f"URL 格式不正确，必须包含协议头(如 http:// 或 https://): '{params.url}'", is_error=True)

    browser = None
    try:
        async with async_playwright() as p:
            # 启动浏览器
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # 设置导航超时时间（例如 15 秒），避免死等
            await page.goto(params.url, wait_until='networkidle', timeout=15000)
            
            html_content = await page.content()

    except TimeoutError:
        return ToolResult(output=f"访问网页超时(超过15秒): {params.url}", is_error=True)

    except Error as e:
        # 捕获 DNS 解析失败、拒绝连接、404/500 等 Playwright 错误
        return ToolResult(output=f"网页加载失败或网络异常: {str(e)}", is_error=True)

    except Exception as e:
        # 捕获其他未知未知异常
        return ToolResult(output=f"获取网页文本时发生未知错误: {str(e)}", is_error=True)
        
    finally:
        # 确保浏览器被关闭，防止内存泄漏
        if browser:
            await browser.close()

    # 3. 解析并提取纯文本
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        for element in soup(['script', 'style', 'header', 'footer', 'nav']):
            element.decompose()

        start_str = "当前网页url是" + params.url + " 以下为该网页的文本内容：" + "\n"
        return ToolResult(output= start_str + soup.get_text(separator='\n', strip=True))
    except Exception as e:
        return ToolResult(output=f"解析 HTML 文本失败: {str(e)}", is_error=True)