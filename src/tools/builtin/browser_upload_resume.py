"""browser_upload_resume 工具：上传 data/CV 中的简历并等待网页解析。"""

from pydantic import BaseModel, Field

from src.browser_mcp.client import call_tool
from src.browser_mcp.fill import parse_snapshot
from src.browser_mcp.upload import find_upload_control, resolve_resume, upload_and_wait
from src.tools import ToolResult, tool


class Params(BaseModel):
    ref: str = Field(
        default="",
        description="简历上传控件的 ref（来自 browser_snapshot）。为空时自动识别上传控件。",
    )
    resume: str = Field(
        default="",
        description="data/CV 中的简历文件名或序号。为空时自动选择；多份简历时返回候选清单，需先询问用户。",
    )


@tool(
    name="browser_upload_resume",
    description=(
        "将 data/CV 中的简历 PDF 上传到投递表单的上传控件，并等待网页解析简历自动填写相关字段。"
        "data/CV 仅一份简历时直接上传；多份时返回候选清单，需先向用户询问用哪一份，"
        "用户答复后再调用本工具并传入 resume 参数。"
    ),
)
async def browser_upload_resume(params: Params):
    target_ref = params.ref.strip()

    if not target_ref:
        snap, err = await call_tool("browser_snapshot", {})
        if err:
            return ToolResult(output=snap, is_error=True)
        control = find_upload_control(parse_snapshot(snap))
        if control is None:
            return ToolResult(
                output="未在当前页面找到简历上传入口（如「选择文件/上传简历」按钮）。",
                is_error=True,
            )
        target_ref = control["ref"]

    choice = resolve_resume(params.resume)
    if choice.action == "ask":
        return ToolResult(output=choice.message)
    if choice.action == "error":
        return ToolResult(output=choice.message, is_error=True)

    text, err = await upload_and_wait(target_ref, choice.path)
    if err:
        return ToolResult(output=f"上传失败：{text}", is_error=True)

    return ToolResult(
        output=(
            f"已上传简历 {choice.path.name}，正在等待网页解析并自动填写相关字段"
            f"（约需数秒）。可再次调用 browser_snapshot 查看解析结果。"
        )
    )
