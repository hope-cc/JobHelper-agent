"""端到端探针：验证「打开表单 → 快照 → 上传简历 → 再快照 → 脱敏填表」流程。

依赖：Playwright MCP 服务已启动（有头）：
    npx @playwright/mcp --port 8931 --user-data-dir "D:/jobhelper-browser-profile"

运行：PYTHONIOENCODING=utf-8 PYTHONPATH=. python scripts/probe_mcp_form.py
"""

from __future__ import annotations

import asyncio
import urllib.parse

from src.api import profile_storage
from src.tools.registry import ToolRegistry

FORM_HTML = """<html><body>
<h1>测试投递表单</h1>
<label>姓名 <input id="name"></label><br>
<label>手机 <input id="phone"></label><br>
<label>学历
  <select id="degree"><option value="">请选择</option><option value="本科">本科</option><option value="硕士">硕士</option></select>
</label><br>
<label>性别 <input type="radio" name="gender" value="男">男 <input type="radio" name="gender" value="女">女</label><br>
<label>自我评价 <textarea id="eval"></textarea></label><br>
<label>简历文件 <input type="file" id="resume"></label><br>
<button>提交申请</button>
</body></html>"""

TEST_PROFILE = {
    "basic_info": {
        "name": "张三",
        "phone": "13800000000",
        "email": "",
        "gender": "男",
        "age": "",
        "location": "广州",
        "id_type": "身份证",
        "id_number": "440101199001011234",
        "id_valid_until": "",
        "hometown": "",
    },
    "education": [],
    "internship": [],
    "project": [],
    "award": [],
    "language": [],
    "self_evaluation": "认真负责，热爱学习",
    "masked_basic_fields": ["phone", "id_number"],
}

# 控件名 → 数据键（模拟 agent 决策映射）
FIELD_TO_DATA_KEY = {
    "姓名": "basic_info.name",
    "手机": "basic_info.phone",
    "学历": "basic_info.nonexist",  # 故意用一个无值键，验证「未匹配」报告
    "性别": "basic_info.gender",
    "自我评价": "self_evaluation",
}


def _snapshot_refs(output: str) -> list[tuple[str, str]]:
    """从 browser_snapshot 输出解析 (ref, 控件名) 列表。"""
    refs = []
    for line in output.splitlines():
        if "]" in line and "「" in line:
            ref = line.split("]")[0].replace("[", "").strip()
            name = line.split("」", 1)[0].split("「")[-1]
            refs.append((ref, name))
    return refs


def _extract_json(text: str) -> str | None:
    """提取首个平衡的 JSON 对象（忽略结果末尾的 Ran Playwright code 段）。"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


async def _dom_values() -> dict:
    """读取浏览器中表单的真实值（验证后台确实填入了真实值）。"""
    import json

    from src.browser_mcp.client import call_tool

    js = (
        "() => {"
        "const inputs=[...document.querySelectorAll('input,select,textarea')]"
        ".map(e => [e.id || e.name, {type: e.type, value: e.value, checked: e.checked}]);"
        "return {inputs: Object.fromEntries(inputs), "
        "checkedRadios:[...document.querySelectorAll('input[type=radio]:checked')].map(e=>e.value)};"
        "}"
    )
    text, err = await call_tool("browser_evaluate", {"function": js})
    if err or not text:
        return {}
    raw = _extract_json(text)
    if raw is None:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


async def main() -> None:
    reg = ToolRegistry.get_instance()
    reg.discover("src.tools.builtin")

    url = "data:text/html;charset=utf-8," + urllib.parse.quote(FORM_HTML)
    print("== browser_navigate ==")
    result = await reg.execute("browser_navigate", {"url": url})
    print(result.output)

    print("\n== browser_snapshot（上传前）==")
    result = await reg.execute("browser_snapshot", {})
    print(result.output)

    print("\n== browser_upload_resume ==")
    result = await reg.execute("browser_upload_resume", {})
    print(result.output)

    print("\n== browser_snapshot（解析后）==")
    result = await reg.execute("browser_snapshot", {})
    print(result.output)

    # 确保有个人信息可填（探针用测试档案）
    if not (profile_storage.load() or {}).get("basic_info", {}).get("name"):
        profile_storage.save(TEST_PROFILE)
        print("\n（未保存个人信息，已写入测试个人信息用于本次验证）")

    print("\n== browser_fill_form ==")
    result = await reg.execute("browser_snapshot", {})
    refs = _snapshot_refs(result.output)
    items = []
    for ref, name in refs:
        for field, data_key in FIELD_TO_DATA_KEY.items():
            if field in name:
                items.append({"ref": ref, "data_key": data_key})
                break
    print("填表映射（ref ← 数据键）:", items)
    result = await reg.execute("browser_fill_form", {"items": items})
    print(result.output)
    print("\n（提示：报告中的手机号应显示为 ***；下面 DOM 回读仅用于验证后台确实填入了真实值）")
    dom = await _dom_values()
    print("DOM 已填值:", {k: v["value"] for k, v in dom.get("inputs", {}).items() if v["value"]})
    print("已勾选 radio:", dom.get("checkedRadios", []))
    print("\n（校验：报告不含真实手机号；DOM 含真实姓名/手机号/性别）")
    from src.browser_mcp.client import close

    await close()


if __name__ == "__main__":
    asyncio.run(main())
