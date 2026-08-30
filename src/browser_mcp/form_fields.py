"""从 browser_snapshot 的 DOM 树中提取三类表单字段字典。

返回三个 {字段名: ref} 字典：
- textboxes：填空框（textbox / textarea / searchbox）
- dropdowns：下拉框（combobox / listbox，或 generic [cursor=pointer] 且浅层含选项容器的元素）
- uploads：简历上传入口（file 输入 / 上传按钮 / 拖拽上传区 / 「上传文件」芯片）

字段名解析规则（统一适用于三类控件）：
1. 优先取控件**同层前序兄弟**中的纯文本标签（如「* 姓名」→「姓名」，去前后星号/空白）；
   前序兄弟不满足时逐级向祖先的上层兄弟查找（处理「+86 手机号」这种前缀混排的情况）；
2. 兜底用控件自身的 name（引号占位文本），仍无法得到语义名则丢弃该控件。

下拉框内部（弹层）的隐藏 textbox（如 `textbox [ref=e121]`）不算填空框，会被排除。
同一字典中字段名重复（如多段经历里的「职位名称」）时保留文档序首个 ref。

与 `src/browser_mcp/dropdown.py` 的下拉框识别规则保持同源：
`combobox`/`listbox` 一律算；generic 需带 `[cursor=pointer]` 且浅层子树有 `list/menu/option`。
"""

from __future__ import annotations

import re

# ---- 行解析 ----

_TREE_ROLES = frozenset([
    "generic", "div", "span", "main", "form", "label", "section",
    "paragraph", "heading", "text", "separator",
    "textbox", "textarea", "searchbox",
    "combobox", "listbox", "checkbox", "radio",
    "button", "link", "img",
    "list", "listitem", "menu", "menubar", "menuitem", "option", "tab",
])

# 填空输入框角色
_TEXT_ROLES = frozenset(["textbox", "textarea", "searchbox"])
# 下拉框角色（不需结构判定）
_DROPDOWN_ROLES = frozenset(["combobox", "listbox"])
# generic [cursor=pointer] 的选项容器（浅层出现其一才算下拉框）
_CONTAINER_ROLES = frozenset(["list", "menu", "menubar", "option"])

# 纯文本容器角色（可充当字段标签）
_LABEL_ROLES = frozenset(["generic", "div", "span", "label", "paragraph", "heading", "text"])

# 下拉框值 / 占位文本等，不应作为字段名
_NON_LABELS = frozenset([
    "请选择", "请输入", "是", "否", "男", "女", "保密", "不限", "全部", "更多",
])

# 非 pointer 的 generic 芯片文本（即“上传文件”小按钮）
_UPLOAD_CHIP_TEXTS = frozenset(["上传文件", "选择文件"])
# 上传按钮 / 拖拽区命中其一即上传入口（含「上传简历」「选择文件」等）
_UPLOAD_KEYWORDS = ("上传", "选择文件", "拖拽", "点击上传", "upload", "resume")
# 动作按钮关键词：名字/文本命中其一则不是上传入口（如「提交简历」「暂存」）
_ACTION_KEYWORDS = ("提交", "搜索", "登录", "投递", "删除", "保存", "下一步", "重置", "取消", "暂存", "预览")

_REF_RE = re.compile(r"\[ref=([^\]]+)\]")
_NAME_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_FLAG_RE = re.compile(r"\[(cursor=pointer|checked|selected|active|disabled)\]")
_ROLE_FIRST = re.compile(r"^([^\s:\"\[\]]+)")

# 标志位归一化：css 属性 → 语义 flag
_FLAG_ALIASES = {"cursor=pointer": "pointer"}


def _strip_quotes(s: str) -> str:
    """去掉首尾成对引号。"""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


class _Node:
    """缩进树节点：角色 / 引号名 / ref / 冒号值 / 标志 / 父子链接。"""

    __slots__ = ("role", "name", "ref", "value", "flags", "parent", "children")

    def __init__(self, role, name="", ref="", value="", flags=None):
        self.role = role
        self.name = name
        self.ref = ref
        self.value = value
        self.flags = flags or frozenset()
        self.parent = None
        self.children = []

    def has(self, flag):
        return flag in self.flags

    @property
    def text(self):
        """自身展示文本：冒号值优先，其次引号名（供纯文本容器充当标签）。"""
        return (self.value or "").strip() or (self.name or "").strip()

    @property
    def subtree_text(self):
        """自身 + 整棵子树的拼接文本（用于上传关键词判定）。"""
        parts = [self.value or "", self.name or ""]
        for c in self.children:
            parts.append(c.subtree_text)
        return "".join(parts)


def parse_line(content: str):
    """解析单个快照行（`- role "name" [ref=x]: value`），非元素行返回 None。"""
    content = content.strip()
    if not content or content.startswith("###") or content.startswith("- /"):
        return None
    if content.startswith("- "):
        content = content[2:].strip()

    m = _ROLE_FIRST.match(content)
    if not m:
        return None
    role = m.group(1).lower()
    if role not in _TREE_ROLES:
        return None

    ref_m = _REF_RE.search(content)
    ref = ref_m.group(1) if ref_m else ""

    name_m = _NAME_RE.search(content)
    name = _strip_quotes(name_m.group(0)) if name_m else ""

    flags = frozenset(_FLAG_ALIASES.get(tok, tok) for tok in _FLAG_RE.findall(content))

    # 取冒号后缀值：去掉角色、引号名、属性组后剩余文本
    rest = content[len(m.group(0)):]
    if name:
        rest = rest.replace(name_m.group(0), "", 1)
    rest = re.sub(r"\[[^\]]*\]", "", rest).strip()
    if rest.startswith(":"):
        rest = rest[1:].strip()
    value = _strip_quotes(rest) if rest else ""

    return _Node(role, name, ref, value, flags)


def build_tree(text: str):
    """把快照文本解析成缩进树，返回虚拟根节点。"""
    root = _Node("root")
    stack = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        node = parse_line(raw)
        if node is None:
            continue
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        node.parent = parent
        parent.children.append(node)
        stack.append((indent, node))
    return root


def walk(root):
    """前序遍历整棵树（文档顺序）。"""
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def _ancestors(node):
    p = node.parent
    while p is not None:
        yield p
        p = p.parent


def _subtree_refs(node, acc):
    """收集子树内所有 ref（用于排除下拉框内部输入框）。"""
    if node.ref:
        acc.add(node.ref)
    for c in node.children:
        _subtree_refs(c, acc)


def _subtree_has_container(node, max_depth=2):
    """node 子树浅层内是否有选项容器（list/menu/option）。"""
    frontier = node.children
    depth = 1
    while frontier and depth <= max_depth:
        nxt = []
        for c in frontier:
            if c.role in _CONTAINER_ROLES:
                return True
            nxt.extend(c.children)
        frontier = nxt
        depth += 1
    return False


# ---- 判定 ----

# 标签块内若出现这些角色，则视为“包含控件的容器”而非纯标签块
_INTERACTIVE_LABEL_ROLES = frozenset([
    "textbox", "textarea", "searchbox", "combobox", "listbox",
    "checkbox", "radio", "button", "link", "img",
])


def _subtree_has_role(node, roles) -> bool:
    for c in node.children:
        if c.role in roles:
            return True
        if _subtree_has_role(c, roles):
            return True
    return False


def _subtree_texts(node) -> list[str]:
    """子树内全部非空文本（文档序）。"""
    out: list[str] = []
    for c in node.children:
        if c.text:
            out.append(c.text)
        out.extend(_subtree_texts(c))
    return out


def _label_from_sibling(sib) -> str:
    """从同层前序兄弟中取字段标签文本。

    兼容两类结构：
    - 纯文本兄弟：`generic: * 姓名`（组合框标签在输入框同层）；
    - 标签块兄弟：`generic > paragraph: 附件简历`（区块内仅一个文字节点，控件在下一行）。
    含控件、或是下拉框/勾选框本身的兄弟不算标签；含多个文字的兄弟是
    「已填字段展示」（如「手机号码 * +86 189-…」），也不是标签。
    """
    if sib.role not in _LABEL_ROLES or sib.has("pointer") or sib.has("checked") or sib.has("selected"):
        return ""
    if sib.children:
        if _subtree_has_role(sib, _INTERACTIVE_LABEL_ROLES):
            return ""
        texts = _subtree_texts(sib)
        if len(texts) != 1:
            return ""
        return texts[0]
    return sib.text


def _clean_label(label: str):
    """去掉前后星号与空白（`* 姓名` → `姓名`）。"""
    label = label.strip()
    while label.startswith("*"):
        label = label[1:].strip()
    while label.endswith("*"):
        label = label[:-1].rstrip()
    return label.strip()


def find_label(node):
    """解析字段名：沿祖先链收集候选文本标签，星号必填标记优先，其次取最近。

    复合字段（如「手机号码」的 `+86` 前缀、「证件号码」的「身份证」证件类型选择器）
    会在同层出现一个更近但非字段名的兄弟文本，因此不能简单地取最近一个。
    站点必填字段标签带 `*`（如「* 姓名」），优先命中可正确跳过前缀。
    """
    candidates: list[tuple[str, int, bool]] = []  # (label, depth, has_star)
    cur = node
    depth = 0
    while cur is not None:
        parent = cur.parent
        if parent is None:
            break
        idx = parent.children.index(cur)
        for sib in reversed(parent.children[:idx]):
            raw_label = _label_from_sibling(sib)
            if not raw_label:
                continue
            label = _clean_label(raw_label)
            if not label or label in _NON_LABELS:
                continue
            if len(label) < 2 or label.startswith("+"):
                continue
            candidates.append((label, depth, "*" in raw_label))
        cur = parent
        depth += 1

    if not candidates:
        own = _clean_label(node.name)
        if own and own not in _NON_LABELS and len(own) >= 2:
            return own
        return ""

    # 最近候选
    immediate = min(candidates, key=lambda c: c[1])
    if immediate[2]:
        # 最近候选本身就是必填标签（* 姓名）
        return immediate[0]
    # 复合字段：同层是前缀（+86 / 身份证），近旁（≤1 层）有星号标签时才覆盖
    star_near = [c for c in candidates if c[2] and c[1] <= 1]
    if star_near:
        return min(star_near, key=lambda c: c[1])[0]
    return immediate[0]


def is_dropdown(node):
    """下拉框判定：combobox/listbox 一律算；generic pointer 需浅层含选项容器。"""
    if node.role in _DROPDOWN_ROLES:
        return True
    if node.role != "generic" or not node.has("pointer"):
        return False
    return _subtree_has_container(node)


def is_textbox(node):
    """填空框判定。"""
    return node.role in _TEXT_ROLES


def is_upload(node):
    """上传入口判定：file 输入 / 上传按钮 / 拖拽区 / 「上传文件」芯片。

    button 需排除动作类名称（「提交简历」「暂存」等含上传关键词但非上传入口）。
    generic [cursor=pointer] 的拖拽区是上传入口；「上传简历」这类纯文本 pointer
    （侧边导航 tab）不算上传。
    """
    body = node.subtree_text
    if node.role == "file":
        return True
    if node.role == "button":
        if any(k in body for k in _ACTION_KEYWORDS):
            return False
        return any(k in body for k in _UPLOAD_KEYWORDS)
    if node.role != "generic":
        return False
    if node.has("pointer"):
        return any(k in body for k in ("拖拽", "选择文件", "点击上传"))
    return (node.value or "").strip() in _UPLOAD_CHIP_TEXTS


def to_map(nodes):
    """把控件节点列表压成 {字段名: ref}，字段名重复时保留文档序首个。"""
    out = {}
    for n in nodes:
        if not n.ref:
            continue
        label = find_label(n)
        if not label:
            continue
        out.setdefault(label, n.ref)
    return out


# ---- 对外入口 ----

def parse_snapshot_fields(text: str) -> dict:
    """解析 browser_snapshot 输出，返回 {textboxes, dropdowns, uploads} 三个字典。

    - textboxes：全部填空框（已排除下拉框弹层内部的隐藏输入框）
    - dropdowns：全部下拉框（含已填 / 未填）
    - uploads：简历上传入口（嵌套在上传区内的小按钮只保留最外层入口）
    """
    root = build_tree(text)
    nodes = list(walk(root))

    dropdowns = [n for n in nodes if is_dropdown(n)]

    # 下拉框弹层内部的 ref（隐藏搜索框等）不算填空框
    inner_refs = set()
    for d in dropdowns:
        _subtree_refs(d, inner_refs)

    textboxes = [
        n for n in nodes
        if is_textbox(n) and n.ref and n.ref not in inner_refs
    ]

    # 上传入口：嵌套在另一个上传入口内部的（如拖拽区里的小“选择文件”按钮）丢弃
    upload_cands = [n for n in nodes if is_upload(n) and n.ref]
    upload_refs = {n.ref for n in upload_cands}
    uploads = [
        n for n in upload_cands
        if not any(p.ref in upload_refs for p in _ancestors(n))
    ]

    return {
        "textboxes": to_map(textboxes),
        "dropdowns": to_map(dropdowns),
        "uploads": to_map(uploads),
    }