"""下拉框识别与填写辅助。

投递表单（如 zhiye.com）的下拉框不是标准 `<select>`/combobox，而是
`generic [cursor=pointer]` 元素（子元素显示「请选择」或当前值），展开后是
`list`/`listitem` 结构。本模块提供程序化识别、快照子树裁切、选项提取
以及展开/收起辅助，供 `browser_probe_dropdowns` / `browser_fill_dropdowns` 两个工具复用。
"""

from __future__ import annotations

import asyncio
import json
import re

from src.browser_mcp.client import call_tool

# 点击后等待渲染/收起的固定短延迟（秒）
EXPAND_WAIT_SECONDS = 0.6
COLLAPSE_WAIT_SECONDS = 0.3

# 下拉框结构规则：generic [cursor=pointer] 且子树含 list 容器
_CURSOR_POINTER = "[cursor=pointer]"
# 显示值占位关键词（未填写）
_PLACEHOLDER_KEYWORDS = ("请选择", "请选")

# 形如 `generic [ref=x]: 文本` / `generic: 文本` 的行
_GENERIC_TEXT_RE = re.compile(r"^generic(?: \[ref=[^\]]+\])?:\s*(.*)$")


def _strip_quotes(s: str) -> str:
    """去掉首尾成对引号。"""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _extract_ref(content: str) -> str:
    m = re.search(r"\[ref=([^\]]+)\]", content)
    return m.group(1) if m else ""


def _strip_lines(text: str) -> list[tuple[int, str]]:
    """把快照文本转为 (indent, content) 列表，跳过空行并去除 "- " 前缀。"""
    out: list[tuple[int, str]] = []
    for raw in text.splitlines():
        s = raw.rstrip()
        if not s.strip():
            continue
        content = s.strip()
        if content.startswith("- "):
            content = content[2:]
        out.append((len(s) - len(s.lstrip()), content))
    return out


def _parse_tree(text: str) -> dict:
    """把快照文本解析为缩进树，返回根节点（indent/content/ref/children）。"""
    root = {"indent": -1, "content": "", "ref": "", "children": []}
    stack = [root]
    for indent, content in _strip_lines(text):
        node = {"indent": indent, "content": content,
                "ref": _extract_ref(content), "children": []}
        while stack and indent <= stack[-1]["indent"]:
            stack.pop()
        stack[-1]["children"].append(node)
        stack.append(node)
    return root


# ---- 识别 ----

def _leading_role(content: str) -> str:
    """取元素行开头的角色词（如 generic / combobox / textbox）。"""
    m = re.match(r"^([a-z]+)", content)
    return m.group(1) if m else ""


# 下拉框角色：无需额外结构判定即可识别
_DROPDOWN_ROLES = {"combobox", "listbox"}
# 选项容器关键词：generic[cursor=pointer] 需在浅层出现其一才算下拉框
_CONTAINER_PREFIXES = ("list", "menu", "option")


def _is_generic_pointer(content: str) -> bool:
    return _leading_role(content) == "generic" and _CURSOR_POINTER in content


def _has_option_container(node: dict, max_depth: int = 2) -> bool:
    """node 子树浅层（默认 2 层）内是否含选项容器。

    用浅层限制区分「下拉框」与「可展开的表单区块」——区块内的 list/menubar
    嵌套层级很深，不会命中浅层检查。
    """
    frontier = node["children"]
    depth = 1
    while frontier and depth <= max_depth:
        nxt: list[dict] = []
        for c in frontier:
            if c["content"].startswith(_CONTAINER_PREFIXES):
                return True
            nxt.extend(c["children"])
        frontier = nxt
        depth += 1
    return False


def _first_display_descendant(node: dict) -> str:
    """子树内首个非空的 `generic...: 文本`，无则返回空串。"""
    for c in node["children"]:
        m = _GENERIC_TEXT_RE.match(c["content"])
        if m and m.group(1).strip():
            return _strip_quotes(m.group(1).strip())
        text = _first_display_descendant(c)
        if text:
            return text
    return ""


def _preceding_sibling_label(parent: dict, child: dict) -> str:
    """取 child 在 parent 中同层前序兄弟的字段标签（形如 `* 籍贯`），无则 ""。"""
    idx = parent["children"].index(child)
    for sib in reversed(parent["children"][:idx]):
        m = _GENERIC_TEXT_RE.match(sib["content"])
        if m and m.group(1).strip():
            return _strip_quotes(m.group(1).strip())
    return ""


def _own_value(content: str) -> str:
    """从元素自身行提取冒号后的当前值（去掉引号名与属性组）。

    例：`combobox "学历" [ref=x]: 本科` → "本科"；`combobox [ref=e154]` → ""。
    """
    s = re.sub(r'"((?:[^"\\]|\\.)*)"', "", content)
    s = re.sub(r"\[[^\]]*\]", "", s)
    if ":" not in s:
        return ""
    return s.split(":", 1)[1].strip()


def find_dropdown_candidates(snapshot_text: str) -> list[dict]:
    """按结构规则识别下拉框候选，返回 [{ref, label, display, is_empty}]。

    识别边界（依据实际站点观察）：
    - 角色为 combobox/listbox 的元素一律视为下拉框；
    - generic 且带 [cursor=pointer] 的元素，需在浅层子树含选项容器（list/menu/option）。
    """
    root = _parse_tree(snapshot_text)
    candidates: list[dict] = []

    def visit(parent: dict) -> None:
        for c in parent["children"]:
            role = _leading_role(c["content"])
            is_dropdown = role in _DROPDOWN_ROLES or (
                _is_generic_pointer(c["content"]) and _has_option_container(c)
            )
            if is_dropdown:
                display = _first_display_descendant(c) or _own_value(c["content"])
                candidates.append({
                    "ref": c["ref"],
                    "label": _preceding_sibling_label(parent, c),
                    "display": display,
                    "is_empty": (not display) or any(
                        k in display for k in _PLACEHOLDER_KEYWORDS
                    ),
                })
            visit(c)

    visit(root)
    return candidates


# ---- 裁切与选项提取 ----

def crop_subtree(snapshot_text: str, ref: str) -> str:
    """裁切出 `[ref=<ref>]` 行起的缩进子树（含后代，不含同级），ref 不存在返回 ""。"""
    target = f"[ref={ref}]"
    lines = snapshot_text.splitlines()
    start = next((i for i, raw in enumerate(lines) if target in raw), None)
    if start is None:
        return ""

    base = len(lines[start]) - len(lines[start].lstrip())

    out = [lines[start]]
    for raw in lines[start + 1:]:
        s = raw.rstrip()
        if not s.strip():
            continue
        content = s.strip()
        if content.startswith("- "):
            content = content[2:]
        indent = len(s) - len(s.lstrip())
        if indent <= base:
            break
        out.append(raw)
    return "\n".join(out)


def _inline_text(content: str) -> str | None:
    """从元素行提取展示文本：generic: 文本 / text: 文本 / 输入控件当前值。"""
    m = _GENERIC_TEXT_RE.match(content)
    if m and m.group(1).strip():
        return _strip_quotes(m.group(1).strip())
    m = re.match(r"^text:\s*(.+)$", content)
    if m and m.group(1).strip():
        return _strip_quotes(m.group(1).strip())
    m = re.match(r"^(?:textbox|textarea|combobox|searchbox)\b.*?:\s*(.+)$", content)
    if m:
        v = m.group(1).strip()
        if v and v != "请输入":  # 占位提示不作为选项文本
            return v
    return None


def _first_text_descendant(node: dict) -> str:
    for c in node["children"]:
        t = _inline_text(c["content"])
        if t:
            return t
        sub = _first_text_descendant(c)
        if sub:
            return sub
    return ""


def _first_ref_descendant(node: dict) -> str:
    for c in node["children"]:
        if c["ref"]:
            return c["ref"]
        sub = _first_ref_descendant(c)
        if sub:
            return sub
    return ""


def _has_selected_marker(node: dict) -> bool:
    if "[selected]" in node["content"]:
        return True
    return any(_has_selected_marker(c) for c in node["children"])


def _option_from_listitem(node: dict) -> dict:
    return {
        "value": _first_text_descendant(node),
        "ref": node["ref"] or _first_ref_descendant(node),
        "selected": _has_selected_marker(node),
    }


def extract_options(subtree: str) -> list[dict]:
    """从展开快照子树提取选项列表 [{value, ref, selected}]。

    优先取 `listitem` 节点（value 取其子树内首个文本，ref 取 listitem 自身或首个带 ref 后代）；
    无 listitem 时兜底解析 `option "x" [ref=y]` 行。无文本的占位节点（如下拉框内的搜索框）被过滤。
    """
    root = _parse_tree(subtree)
    options: list[dict] = []

    def walk(node: dict) -> None:
        for c in node["children"]:
            if c["content"].startswith("listitem"):
                options.append(_option_from_listitem(c))
            walk(c)

    walk(root)
    if not options:
        for _, content in _strip_lines(subtree):
            m = re.match(r'^option\s+"((?:[^"\\]|\\.)*)"(?:\s+\[ref=([^\]]+)\])?', content)
            if m:
                options.append({
                    "value": m.group(1),
                    "ref": m.group(2) or "",
                    "selected": "[selected]" in content,
                })
    return [o for o in options if o["value"]]


def find_option_ref(options: list[dict], target: str) -> tuple[str | None, str | None]:
    """在选项中匹配目标值，返回 (可点击 ref, 命中的选项值)；未命中返回 (None, None)。

    ref 为空（选项不可点击）时返回 (None, 命中的选项值)。
    """
    for opt in options:
        if opt.get("value") == target:
            return (opt.get("ref") or None), opt.get("value")
    for opt in options:
        if target and target in opt.get("value", ""):
            return (opt.get("ref") or None), opt.get("value")
    return None, None


# ---- 展开/收起辅助（连真实 MCP）----

async def expand_and_crop(ref: str) -> tuple[str, str]:
    """点击展开下拉框，等待渲染后取快照并裁切为该下拉框子树。

    返回 (子树文本, 错误信息)；出错时子树为空串。
    """
    text, err = await call_tool("browser_click", {"target": ref})
    if err:
        return "", f"展开点击失败：{text}"
    await asyncio.sleep(EXPAND_WAIT_SECONDS)
    snap, err = await call_tool("browser_snapshot", {})
    if err:
        return "", f"展开后快照失败：{snap}"
    cropped = crop_subtree(snap, ref)
    if not cropped:
        return "", f"展开后未在快照中找到 [ref={ref}] 的子树"
    return cropped, ""


async def collapse(ref: str) -> tuple[str, bool]:
    """再次点击同一 ref 收起下拉框（toggle），返回 (内容, is_error)。"""
    text, err = await call_tool("browser_click", {"target": ref})
    await asyncio.sleep(COLLAPSE_WAIT_SECONDS)
    return text, err


# ---- 过滤型 combobox / 确定按钮 / 文本点击 ----

# 展开后等待过滤渲染的时长
FILTER_WAIT_SECONDS = 0.6

# 确认类按钮关键词（限定为弹层「确定/确认」，避免误点表单级「保存/提交」）
CONFIRM_KEYWORDS = ("确定", "确认")


def _accessible_name(content: str) -> str:
    """取元素行的可访问名称（引号内文本），如 `button "确定" [ref=x]` → "确定"。"""
    m = re.search(r'"((?:[^"\\]|\\.)*)"', content)
    return _strip_quotes(m.group(1)) if m else ""


def find_filter_input(subtree: str) -> str:
    """在展开下拉框子树中找过滤/搜索输入框 ref（textbox/searchbox 后代），无则 ""。"""
    root = _parse_tree(subtree)

    def walk(node: dict) -> str:
        for c in node["children"]:
            if _leading_role(c["content"]) in ("textbox", "searchbox"):
                return c["ref"]
            r = walk(c)
            if r:
                return r
        return ""

    return walk(root)


def find_confirm_button_ref(snapshot_text: str) -> str:
    """在快照中找最后一个名字含确认关键词的 button/link ref（弹层确定按钮通常最后渲染）。"""
    root = _parse_tree(snapshot_text)
    matches: list[str] = []

    def walk(node: dict) -> None:
        for c in node["children"]:
            role = _leading_role(c["content"])
            if role in ("button", "link"):
                name = _accessible_name(c["content"])
                if name and any(k in name for k in CONFIRM_KEYWORDS):
                    matches.append(c["ref"])
            walk(c)

    walk(root)
    return matches[-1] if matches else ""


def extract_ref_from_text(text: str) -> str:
    """从工具响应文本中提取 `[ref=X]`，无则 ""。"""
    m = re.search(r"\[ref=([^\]]+)\]", text or "")
    return m.group(1) if m else ""


async def click_text(target_text: str) -> tuple[bool, str]:
    """用 browser_find 按文本定位页面元素并点击。返回 (是否成功, 说明)。"""
    resp, err = await call_tool("browser_find", {"text": target_text})
    if err:
        return False, f"browser_find 失败：{resp}"
    ref = extract_ref_from_text(resp)
    if not ref:
        return False, f"browser_find 未返回可点击 ref：{resp[:100]}"
    text, err2 = await call_tool("browser_click", {"target": ref})
    if err2:
        return False, f"点击失败：{text}"
    return True, f"已按文本点击「{target_text}」"


async def click_option_by_js(value: str) -> tuple[bool, str]:
    """JS 兜底：用 page.getByText 精确匹配并点击页面中可见的目标选项文本。"""
    code = (
        "async ({ page }) => {\n"
        f"  const loc = page.getByText({json.dumps(value, ensure_ascii=False)}, {{ exact: true }});\n"
        "  await loc.last().click();\n"
        "}"
    )
    text, err = await call_tool("browser_run_code_unsafe", {"code": code})
    if err:
        return False, f"JS 点击失败：{text}"
    return True, "已通过 JS 点击"


async def select_by_text(value: str) -> tuple[bool, str]:
    """按文本选择选项：browser_find 优先，失败回退 JS。返回 (是否成功, 说明)。"""
    ok, msg = await click_text(value)
    if ok:
        return True, msg
    return await click_option_by_js(value)
