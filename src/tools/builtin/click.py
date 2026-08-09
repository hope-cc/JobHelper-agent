import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError
from pydantic import BaseModel, Field
from urllib.parse import urlparse


from src.tools import tool, ToolResult

class Params(BaseModel):
    url: str = Field(default="", description="网页的url链接")
    text: str = Field(default="", description="要点击的文本")

@tool(name="click", description="点击指定文本后获取网页文本内容，支持新标签页跳转和当前页刷新")
async def click(params: Params):
    url = params.url
    text = params.text

    # url和text为空校验
    if not url:
        return ToolResult(output="URL 不能为空", is_error=True)
    if not text:
        return ToolResult(output="要点击的文本不能为空", is_error=True)

    #URL 格式规范校验
    parsed_url = urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        return ToolResult(output=f"URL 格式不正确，必须包含协议头(如 http:// 或 https://): '{params.url}'", is_error=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto(url, wait_until='networkidle')
        
        target = page.get_by_text(text)
        try:
            if await target.count() == 1:
                # 记录点击前的 DOM 文本，用于判断 AJAX 无跳转刷新
                old_html = await page.content()
                
                try:
                    # 尝试监听新标签页（针对点击后打开新窗口的链接）
                    async with page.expect_popup(timeout=3000) as popup_info:
                        await target.first.click()
                    
                    # 情况 1：成功捕获到弹出的新标签页
                    active_page = await popup_info.value
                    await active_page.wait_for_load_state('networkidle')

                except TimeoutError:
                    # 情况 2：未弹新窗口，说明在当前页跳转或 AJAX 局部刷新
                    active_page = page
                    
                    # 等待网络空闲
                    try:
                        await active_page.wait_for_load_state('networkidle', timeout=3000)
                    except Exception:
                        pass

                    # 如果 URL 没变，等待 DOM 内容更新
                    for _ in range(10):
                        new_html = await active_page.content()
                        if new_html != old_html:
                            break
                        await asyncio.sleep(0.5)

                # 统一提取活跃页面（无论是新标签页还是当前页）的文本
                final_html = await active_page.content()
                soup = BeautifulSoup(final_html, 'html.parser')
                for element in soup(['script', 'style', 'header', 'footer', 'nav']):
                    element.decompose()
                
                clean_text = soup.get_text(separator='\n', strip=True)
                start_str = "当前网页url是" + url + " 以下为该网页的文本内容：" + "\n"
                return ToolResult(output= start_str + clean_text)

            elif await target.count():
                return ToolResult(output=f"未找到目标文字: {text}", is_error=True)
            else:
                return ToolResult(output=f"找到多个目标文字: {text}，请提供更精确的文本", is_error=True)
            
        finally:
            await browser.close()