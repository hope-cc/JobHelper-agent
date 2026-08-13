"""browser_snapshot 工具：获取当前网页表单快照。

返回**原始快照结构**（含字段标签、下拉选项等），仅去除文本长度 > 100 的
无意义长文本节点（如公司声明、长段说明），以便 agent 识别字段与标签的对应关系。
"""

from pydantic import BaseModel

from src.browser_mcp.client import call_tool
from src.tools import ToolResult, tool

# 超过该长度的内联文本视为无意义长文本（公司声明等），从快照中剔除
_MAX_FIELD_TEXT_LEN = 100


def _strip_snapshot_long_text(text: str) -> str:
    """保留原始快照结构，仅去除带 [ref=] 且内联文本长度 > 100 的节点。

    Page URL 等元信息行不带 [ref=]，不会被过滤。
    """
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        content = line.strip()
        if content.startswith("- "):
            content = content[2:]
        if "[ref=" not in content:
            out.append(line)
            continue

        inline = ""
        if ": " in content:
            inline = content.split(": ", 1)[1].strip()
        if len(inline) >= 2 and inline[0] == '"' and inline[-1] == '"':
            inline = inline[1:-1]
        if len(inline) > _MAX_FIELD_TEXT_LEN:
            continue  # 无意义长文本，去除该节点行
        out.append(line)
    return "\n".join(out)


class Params(BaseModel):
    """无参数。"""


@tool(
    name="browser_snapshot",
    description=(
        "获取当前网页的表单快照，返回原始快照结构（含字段标签、下拉选项、上传入口），"
        "仅去除公司声明等无意义长文本。用于识别待填字段、下拉选项与上传入口。"
        "下拉框（generic [cursor=pointer]）的选项识别与探测请使用 browser_probe_dropdowns。"
    ),
)
async def browser_snapshot(params: Params):
    text, err = await call_tool("browser_snapshot", {})
    if err:
        return ToolResult(output=text, is_error=True)
    return ToolResult(output=_strip_snapshot_long_text(text))
