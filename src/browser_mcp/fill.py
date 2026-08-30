"""表单快照解析与填表辅助。

- `parse_snapshot`：解析 MCP `browser_snapshot` 输出为控件字典列表
- 控件判定：上传候选 / 可填控件 / 单选复选 / 动作按钮
- 脱敏取值：从个人信息取真实值、按脱敏标记显示 ***、下拉选项匹配
"""

from __future__ import annotations

import re
from typing import Any

# 控件角色常量
ROLE_TYPES = {
    "textbox",
    "textarea",
    "searchbox",
    "combobox",
    "radio",
    "checkbox",
    "button",
    "file",
}

# 上传入口关键词（按钮名）
_UPLOAD_KEYWORDS = ("上传", "选择文件", "简历文件", "拖拽", "upload", "resume", "简历")
# 动作按钮关键词（排除在上传候选之外）
_ACTION_KEYWORDS = ("提交", "搜索", "登录", "投递", "删除", "保存", "下一步", "重置")


def _el(ref: str = "", role: str = "", name: str = "") -> dict:
    """构造一个快照元素字典（与 parse_snapshot 返回结构一致）。"""
    return {
        "ref": ref,
        "role": role,
        "name": name,
        "value": "",
        "selected": False,
        "options": [],
    }


def _strip_quotes(s: str) -> str:
    """去掉首尾成对引号。"""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _parse_element_line(content: str) -> dict | None:
    """解析单个元素行，返回元素字典；无法解析返回 None。

    兼容格式：
    - `textbox "姓名" [ref=e4]`（角色+引号名称+属性）
    - `textbox "姓名" [ref=e4]: 张三`（同上，冒号后为当前值）
    - `textbox [ref=2]: 姓名`（无引号名称，冒号后为名称——旧格式）
    - `[ref=2] textbox "姓名" [required]`（ref 前置）
    - `checkbox "同意协议" [checked] [ref=e13]`（勾选标记）
    - `text: 姓名` / `heading "标题"` / `Page URL: x` 等非交互元素
    """
    content = content.strip()
    if not content:
        return None
    # 非交互元素：text / heading / 元信息
    if content.startswith(("text:", "heading", "Page URL", "Press Esc", "link", "img", "separator")):
        return None

    # 提取 ref
    ref_match = re.search(r"\[ref=([^\]]+)\]", content)
    ref = ref_match.group(1) if ref_match else ""

    # 提取引号名称
    name_match = re.search(r'"((?:[^"\\]|\\.)*)"', content)
    name = _strip_quotes(name_match.group(0)) if name_match else ""

    # 提取角色：扫描第一个已知控件角色词（兼容 `[ref=2] textbox ...` 旧格式）
    tokens = re.findall(r"[A-Za-z]+", content)
    role = next((t.lower() for t in tokens if t.lower() in ROLE_TYPES), None)
    if role is None:
        return None

    el = _el(ref=ref, role=role, name=name)
    el["selected"] = "[checked]" in content

    # 冒号后缀：有引号名称 → 值为后缀；无引号名称 → 名称为后缀
    if ":" in content:
        suffix = content.split(":", 1)[1].strip()
        if suffix:
            if name:
                el["value"] = _strip_quotes(suffix)
            else:
                el["name"] = _strip_quotes(suffix)

    return el


def _parse_option_line(content: str) -> dict | None:
    """解析 option 子行，如 `option "请选择" [selected]`。"""
    content = content.strip()
    if not content.startswith("option "):
        return None
    body = content[len("option "):].strip()
    value = _strip_quotes(body.split(" [", 1)[0].strip())
    return {"value": value, "selected": "[selected]" in content}


def parse_snapshot(text: str) -> list[dict]:
    """解析 MCP `browser_snapshot` 输出为元素字典列表。

    返回元素结构：{ref, role, name, value, selected, options}
    - options 为下拉/单选候选：[{value, selected}]
    - 单选选项值从同层级的邻近 text 行推导
    - generic/heading/text 等非交互容器不返回
    """
    # (indent, content) 预处理，跳过空行与元信息行
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        s = raw.rstrip()
        if not s.strip():
            continue
        content = s.strip()
        if content.startswith(("Page URL", "Press Esc")):
            continue
        if content.startswith("- "):
            content = content[2:]
        indent = len(s) - len(s.lstrip())
        lines.append((indent, content))

    elements: list[dict] = []
    # 下拉栈：记录尚未闭合的 combobox（indent, 元素）
    combobox_stack: list[tuple[int, dict]] = []
    # 每个缩进层级上最近一个待赋选项的单选元素（用于从邻近 text 推导选项）
    pending_radio: dict[int, dict] = {}

    for indent, content in lines:
        # 离开更低层级：弹出闭合的 combobox
        while combobox_stack and indent <= combobox_stack[-1][0]:
            combobox_stack.pop()

        option = _parse_option_line(content)
        if option is not None:
            if combobox_stack:
                combobox_stack[-1][1]["options"].append(option)
            continue

        el = _parse_element_line(content)
        if el is None:
            # text 行：若存在待赋选项的单选，则作为其选项值
            text_match = re.match(r"^text:\s*(.+)$", content)
            if text_match and pending_radio.get(indent):
                pending_radio[indent]["options"].append(
                    {"value": text_match.group(1).strip(), "selected": False}
                )
                pending_radio.pop(indent, None)
            continue

        elements.append(el)

        if el["role"] == "combobox":
            combobox_stack.append((indent, el))
        elif el["role"] == "radio":
            pending_radio[indent] = el

    return elements


# ---- 控件判定 ----

def is_upload_candidate(el: dict) -> bool:
    """是否为简历上传入口（按钮名含上传关键词，或 file 输入）。"""
    role = el.get("role", "")
    name = el.get("name", "")
    if role == "file":
        return True
    if role != "button":
        return False
    if not name:
        return False
    if any(k in name for k in _ACTION_KEYWORDS):
        return False
    return any(k.lower() in name.lower() for k in _UPLOAD_KEYWORDS)


def is_action_button(el: dict) -> bool:
    """是否为动作按钮（提交/搜索/登录等）。"""
    return el.get("role") in ("button", "link") and any(
        k in el.get("name", "") for k in _ACTION_KEYWORDS
    )


def is_fillable(el: dict) -> bool:
    """是否为可填控件（输入框/文本域/下拉框）。"""
    return el.get("role") in ("textbox", "textarea", "searchbox", "combobox")


def is_option_el(el: dict) -> bool:
    """是否为单选/复选控件。"""
    return el.get("role") in ("radio", "checkbox")


def has_value(el: dict) -> bool:
    """控件是否已有值（文本非空 / 已勾选）。"""
    if el.get("role") in ("radio", "checkbox"):
        return bool(el.get("selected"))
    return bool(el.get("value"))


def match_combobox_value(options: list[dict], value: str) -> str | None:
    """在下拉选项中匹配真实值（精确优先，其次包含），返回匹配到的选项值。"""
    for opt in options:
        ov = opt.get("value", "")
        if ov == value:
            return ov
    for opt in options:
        ov = opt.get("value", "")
        if value and value in ov:
            return ov
    return None


def _option_matches(el: dict, value: str) -> bool:
    """元素 options 中是否存在等于 value 的选项。"""
    return any(opt.get("value") == value for opt in el.get("options", []))


def find_radio_ref(elements: list[dict], value: str) -> str | None:
    """在单选组中查找值为 value 的选项控件 ref；未找到返回 None。"""
    # 优先按选项值精确匹配
    for e in elements:
        if e["role"] == "radio" and _option_matches(e, value):
            return e["ref"]
    # 兜底：按控件名称包含匹配
    for e in elements:
        if e["role"] == "radio" and value and value in e.get("name", ""):
            return e["ref"]
    return None
