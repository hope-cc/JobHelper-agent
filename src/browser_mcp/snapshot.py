
"""
把 browser_snapshot（Playwright MCP 的 Accessibility Snapshot）解析成三个字典：

    填空   (textbox):  {'字段名': 'ref'}
    下拉框 (dropdown):  {'字段名': 'ref'}
    简历上传 (upload):  {'字段名': 'ref'}

用法:
    result = process_browser_snapshot(snapshot_text)
    result['textbox']   # {'姓名': 'e112', ...}
    result['dropdown']  # {'籍贯': 'e298', ...}
    result['upload']    # {'附件简历': 'e96', ...}

规则:
- 填空: 字段标签后面的 textbox，如  `generic: 姓名 *` + `textbox [ref=e112]` -> {'姓名': 'e112'}
- 下拉框: 字段标签后面的 combobox（带头指针或不带均可）；combobox 内嵌 menubar 的
         （如"期望工作地点"，内部 textbox 只是过滤输入）也归下拉框；
         generic [cursor=pointer] 内含有 list/menubar/listitem 的也算；
         combobox 里若内嵌可输入的 textbox（如"学校名称"），归到 textbox 而非下拉框。
- 上传:  文本为"选择文件/上传文件/上传简历"，或子树含"拖拽/点击上传"的控件；
         仅保留字段名里带"简历"的（附件简历 / 上传简历 / 简历附件）。
- 字段名重复时自动加 _2、_3 后缀保留全部。
"""

import re
from src.browser_mcp.client import call_tool

NODE_RE = re.compile(r'^(\s*)- ([^\s\[]+)(.*)$')
ATTR_RE = re.compile(r'\[([^\]]+)\]')
CJK_RE = re.compile(r'[一-鿿]')

# 这些文本不当作字段标签
_EXACT_NOISE = {
    '请选择', '选择', '是', '否', '男', '女', '保密', '无', '至今',
    '搜索', '添加', '取消', '确定', '选择文件', '上传文件',
    '清空', '保存', '预览', '暂存', '提交', '投递', '首页', '选择',
}
_PREFIX_NOISE = (
    '请选择', '拖拽', '支持', '搜索', '添加', '将你的',
    '已选', '请在',
)


class Node:
    __slots__ = ('type', 'ref', 'attrs', 'text', 'children', 'depth', 'parent')

    def __init__(self, type_, ref, attrs, text, depth):
        self.type = type_
        self.ref = ref
        self.attrs = set(attrs)
        self.text = text
        self.children = []
        self.depth = depth
        self.parent = None

    @property
    def cursor(self):
        return 'cursor=pointer' in self.attrs

    def __repr__(self):
        return f'<{self.type} {self.ref} {self.text!r}>'


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


def parse_snapshot(text):
    """把 snapshot 的 markdown 提取出 ```yaml 块并解析成 DOM 树。"""
    lines = text.splitlines()
    yaml_lines, inside = [], False
    for ln in lines:
        if re.match(r'^\s*```', ln):
            inside = not inside
            continue
        if inside:
            yaml_lines.append(ln)
    if not yaml_lines:  # 没有代码围栏时，把全文当 yaml 解析
        yaml_lines = [ln for ln in lines if ln.strip()]

    root = Node('root', None, [], '', -1)
    stack = []  # (depth, node)

    for ln in yaml_lines:
        if not ln.strip() or ln.lstrip().startswith('#'):
            continue
        m = NODE_RE.match(ln)
        if not m:
            continue
        indent, type_, rest = m.groups()
        type_ = type_.rstrip(':')          # `text: 拖拽...` 这类类型后紧跟冒号
        depth = len(indent)

        attrs = ATTR_RE.findall(rest)
        rest = ATTR_RE.sub(' ', rest).strip()

        text = ''
        if rest.startswith('"'):
            qm = re.match(r'^"((?:[^"\\]|\\.)*)"\s*(.*)$', rest)
            if qm:
                text, rest = qm.group(1), qm.group(2).strip()
            else:
                rest = ''
        if rest.startswith(':'):
            content = _unquote(rest[1:].strip())
            if content:
                text = content
        elif rest:                          # 裸内容，如 `text: 拖拽或点击上传简历...`
            text = _unquote(rest)

        node = Node(type_, None, attrs, text, depth)
        for a in attrs:
            if a.startswith('ref='):
                node.ref = a.split('=', 1)[1]
                break

        while stack and stack[-1][0] >= depth:
            stack.pop()
        if stack:
            node.parent = stack[-1][1]
            stack[-1][1].children.append(node)
        else:
            node.parent = root
            root.children.append(node)
        stack.append((depth, node))
    return root


def _walk(nodes):
    """先序遍历（文档顺序）。"""
    out = []
    for n in nodes:
        out.append(n)
        out.extend(_walk(n.children))
    return out


def _subtree_text(n):
    parts = []
    stack = [n]
    while stack:
        x = stack.pop()
        if x is not n and x.text:
            parts.append(x.text)
        stack.extend(reversed(x.children))
    return ' '.join(parts)


def _inside_dropdown_like(n):
    """标签是否位于下拉框/组合框内部（其值文本不应作为字段标签）。"""
    cur = n.parent
    while cur is not None and cur.type != 'root':
        if cur.type == 'combobox':
            return True
        if cur.cursor and _has_desc(cur, {'list', 'menubar', 'listitem'}, max_depth=1):
            return True
        cur = cur.parent
    return False


def _is_label_candidate(n):
    """叶子节点 + 含中文 + 非交互 + 非噪声，才算字段标签。"""
    if not n.text or n.children or n.cursor:
        return False
    if _inside_dropdown_like(n):
        return False
    if n.type not in ('generic', 'paragraph'):
        return False
    t = n.text
    if not CJK_RE.search(t):
        return False
    if re.match(r'^\d+/\d+$', t):            # 0/2000
        return False
    if re.match(r'^[+\-]?\d[\d\s.\-]*$', t):  # 手机号 / +86 / "3"
        return False
    if t in _EXACT_NOISE:
        return False
    if t.startswith(_PREFIX_NOISE):
        return False
    return True


def _labels_in(sib, depth_cap=2):
    """sib 子树里可能的字段标签；超过 2 个就当是导航/菜单容器，返回空。"""
    found = []
    stack = [sib]
    while stack:
        n = stack.pop()
        if n.children:
            stack.extend(reversed(n.children))
        elif _is_label_candidate(n) and (n.depth - sib.depth) <= depth_cap:
            found.append(n)
    if len(found) > 2:
        return []
    return found


def _nearest_label(sib):
    found = _labels_in(sib)
    return found[-1] if found else None


def _find_label(node):
    """从控件向上回溯，找最近的前一个字段标签。"""
    cur, parent = node, node.parent
    while parent is not None:
        idx = parent.children.index(cur)
        for sib in reversed(parent.children[:idx]):
            lab = _nearest_label(sib)
            if lab:
                return lab
        cur, parent = parent, parent.parent
    return None


def _clean_label(text):
    return ' '.join(text.replace('*', '').replace('　', ' ').split())


def _dedup(items):
    """同名加 _2/_3 后缀。items: [(label, ref)] 按文档顺序。"""
    out, seen = {}, {}
    for label, ref in items:
        n = seen.get(label, 0) + 1
        seen[label] = n
        key = label if n == 1 else f'{label}_{n}'
        out[key] = ref
    return out


def _has_desc(n, types, max_depth=None):
    """n 的子树里（深度不超过 max_depth 时）是否存在指定类型节点。"""
    stack = [(c, 1) for c in reversed(n.children)]
    while stack:
        x, d = stack.pop()
        if x.type in types:
            return True
        if max_depth is not None and d >= max_depth:
            continue
        stack.extend((c, d + 1) for c in reversed(x.children))
    return False


def _has_inline_value(content: str) -> bool:
    """快照行是否带已填值：存在引号名，且其后的冒号后为非空值。

    例：`textbox "请输入" [ref=e187]: "18928733892"` → True；
    `textbox "请输入" [ref=e168]`（无冒号）、`textbox "专业 *" [ref=e288]:`
    （冒号后为空，占位在子行）→ False；
    旧格式 `role [ref=2]: 名称` / `generic: 投递意向` 的冒号后是标签/名称 → False。
    """
    content = content.strip()
    content = content[2:] if content.startswith("- ") else content

    # 无引号名：冒号后缀是标签/名称（旧格式），不是值
    name_m = re.search(r'"((?:[^"\\]|\\.)*)"', content)
    if not name_m:
        return False

    rest = ATTR_RE.sub(" ", content[name_m.end():]).strip()
    if not rest.startswith(":"):
        return False
    return bool(_unquote(rest[1:].strip()))


# 下拉框内部的容器/控件子节点：其文本不是「已选值」展示
_DROPDOWN_VALUE_SKIP_TYPES = ('list', 'menubar', 'listitem', 'textbox', 'checkbox', 'radio')


def _has_dropdown_value(node) -> bool:
    """下拉目标节点是否已选值：存在非占位文本的直接子节点。

    站点选中后会在触发节点内渲染一个显示已选值的节点（如 `generic [ref=e318]: 中国`），
    未选则显示占位 `请选择` 或没有显示节点。容器子节点（选项列表 / 过滤输入）不算。
    """
    for c in node.children:
        if c.type in _DROPDOWN_VALUE_SKIP_TYPES:
            continue
        t = (c.text or "").strip()
        if not t:
            continue
        if t == "请选择" or t == "选择" or t.startswith("请选择"):
            continue
        return True
    return False


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


async def process_browser_snapshot() -> dict:
    text, err = await call_tool("browser_snapshot", {})
    text = _strip_snapshot_long_text(text)

    # 行内已带值（textbox `...: 值`）的控件 ref，填充时跳过
    filled_refs: set[str] = set()
    for raw in text.splitlines():
        content = raw.strip()
        if _has_inline_value(content):
            m = re.search(r"\[ref=([^\]]+)\]", content)
            if m:
                filled_refs.add(m.group(1))

    root = parse_snapshot(text)
    all_nodes = _walk(root.children)

    # ---- 1. 下拉框目标 ----
    dropdown_targets = []
    for n in all_nodes:
        if n.type == 'combobox' and n.ref:
            if _has_desc(n, {'menubar'}):
                dropdown_targets.append(n)      # combobox 内有 menubar：选择型下拉（期望工作地点 → e199）
            elif not _has_desc(n, {'textbox'}):
                dropdown_targets.append(n)      # 无输入框的 combobox（学历 → e259）
            # 其余（含 list 搜索输入的 combobox，如学校名称 → e249）由内部 textbox 当填空
        elif (n.type == 'generic' and n.cursor and n.ref
                and _has_desc(n, {'list', 'menubar', 'listitem'}, max_depth=1)):
            dropdown_targets.append(n)                      # generic [cursor=pointer] 直接包着下拉列表
    dd_set = set(id(x) for x in dropdown_targets)

    def inside_dropdown(n):
        cur = n
        while cur is not None:
            if id(cur) in dd_set:
                return True
            cur = cur.parent
        return False

    # ---- 2. 填空(textbox)目标 ----
    textbox_entries = []
    for n in all_nodes:
        if n.type != 'textbox' or not n.ref:
            continue
        if n.text.startswith('搜索'):        # 页内搜索框，不是表单字段
            continue
        if inside_dropdown(n):               # 下拉框内部用来过滤的隐藏输入，跳过
            continue
        if n.ref in filled_refs:             # 已填（行内带值），跳过
            continue
        lab = _find_label(n)
        if lab:
            textbox_entries.append((_clean_label(lab.text), n.ref))

    # ---- 3. 上传目标 ----
    upload_cands = []
    for n in all_nodes:
        if n.type not in ('button', 'generic') or not n.ref:
            continue
        txt = n.text
        if txt in ('选择文件', '上传文件', '上传简历'):
            if n.type == 'button':
                rank = 3
            elif n.cursor:
                rank = 3 if n.children else 0   # 纯文本的 cursor=pointer 疑似导航/链接
            else:
                rank = 1
            upload_cands.append((n, rank))
        elif '拖拽' in _subtree_text(n) or '点击上传' in _subtree_text(n):
            upload_cands.append((n, 2))

    dropdown_entries = []
    for n in dropdown_targets:
        if n.ref in filled_refs or _has_dropdown_value(n):  # 已填，跳过
            continue
        lab = _find_label(n)
        if lab:
            dropdown_entries.append((_clean_label(lab.text), n.ref))

    # 上传: 同一字段名取等级最高的（拖拽上传区 > "选择文件"按钮 > 普通"上传文件" > 导航项）
    upload_best = {}
    for order, (n, rank) in enumerate(upload_cands):
        lab_node = _find_label(n)
        if lab_node is None:
            continue
        lab = _clean_label(lab_node.text)
        prev = upload_best.get(lab)
        if prev is None or (rank, -order) > (prev[0], -prev[1]):
            upload_best[lab] = (rank, order, n.ref)
    upload_entries = [
        (lab, ref)
        for lab, (rank, order, ref) in upload_best.items()
        if '简历' in lab                       # 只保留简历相关上传
    ]

    # ---- 4. 汇总（同名自动加后缀）----
    return _dedup(textbox_entries),_dedup(dropdown_entries),_dedup(upload_entries),
    
