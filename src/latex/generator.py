"""LaTeX 代码生成器。

将简历 JSON 数据（blocks + connections）转换为完整的 LaTeX 源码。
"""

from dataclasses import dataclass, field
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "CV"


# ---- 字段访问辅助（兼容 camelCase / snake_case） ----

def _get_field(obj: dict, *keys: str, default=None):
    """按优先级查找字段值，支持 camelCase 和 snake_case 兼容。"""
    for k in keys:
        if k in obj:
            return obj[k]
    return default


def _content_field(content: dict, *keys: str, default=None):
    """获取 content 子字段，兼容 camelCase/snake_case。"""
    return _get_field(content, *keys, default=default)


def _personal_field(info: dict, *keys: str, default=None):
    """获取 personalInfo 子字段，兼容 camelCase/snake_case。"""
    return _get_field(info, *keys, default=default)


@dataclass
class SectionGroup:
    """同一模块类型的连续正文块分组。"""
    category: str
    blocks: list[dict] = field(default_factory=list)


def _sort_blocks(blocks: list[dict], connections: list[dict]) -> list[dict]:
    """按连线链遍历排序，返回有序 block 列表。

    从 personal_info 块开始沿 connections 单向链路遍历。
    无连线时回退到原始顺序。
    """
    if not connections:
        return blocks

    block_map = {b.get("id", ""): b for b in blocks}

    # 兼容 camelCase 和 snake_case 字段名
    def _from_id(c):
        return c.get("fromBlockId") or c.get("from_block_id") or ""
    def _to_id(c):
        return c.get("toBlockId") or c.get("to_block_id") or ""

    # 构建邻接表：from → to
    adj: dict[str, str] = {}
    for c in connections:
        fid = _from_id(c)
        tid = _to_id(c)
        if fid and tid:
            adj[fid] = tid

    # 找起点：personal_info 且没有入边的块
    has_incoming = {_to_id(c) for c in connections if _to_id(c)}
    starts = [
        b for b in blocks
        if b.get("type") == "personal_info" and b["id"] not in has_incoming
    ]
    # 如果没有无入边的 personal_info，找到第一个 personal_info
    if not starts:
        starts = [b for b in blocks if b.get("type") == "personal_info"]
    # 如果还是找不到，用 blocks 原始顺序中最前面的
    if not starts:
        return blocks

    visited: set[str] = set()
    result: list[dict] = []

    current_id = starts[0]["id"]
    while current_id and current_id not in visited:
        b = block_map.get(current_id)
        if b:
            result.append(b)
            visited.add(current_id)
        current_id = adj.get(current_id, "")

    # 追加未被链到的块（如独立块）
    for b in blocks:
        if b["id"] not in visited:
            result.append(b)

    return result


def _group_sections(sorted_blocks: list[dict]) -> list[SectionGroup]:
    """将排序后的正文块按连续相同 category 分组。"""
    groups: list[SectionGroup] = []
    current: SectionGroup | None = None

    for b in sorted_blocks:
        if b.get("type") != "content":
            continue
        content = _get_field(b, "content", default={})
        cat = _content_field(content, "category", default="其他")
        if current and current.category == cat:
            current.blocks.append(b)
        else:
            if current:
                groups.append(current)
            current = SectionGroup(category=cat, blocks=[b])

    if current:
        groups.append(current)

    return groups


def _escape_latex(text: str) -> str:
    """转义 LaTeX 特殊字符。"""
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\^{}",
        "\\": r"\textbackslash{}",
    }
    for ch, repl in replacements.items():
        text = text.replace(ch, repl)
    return text


def _spans_to_latex(spans: list[dict], bullet_points: bool) -> str:
    """将 TextSpan 列表转换为 LaTeX 行内文本。

    加粗 → \\textbf{...}
    换行 → \\\\
    圆点列表 → itemize 环境
    """
    if not spans:
        return ""

    # 先拼接为纯文本 + 加粗标记
    parts: list[str] = []
    for s in spans:
        text = _escape_latex(s.get("text", ""))
        if s.get("bold"):
            parts.append(r"\textbf{" + text + "}")
        else:
            parts.append(text)

    latex = "".join(parts)

    # 处理换行：\\n → latex 换行
    lines = latex.split("\n")
    lines = [l.strip() for l in lines if l.strip()]

    if not lines:
        return ""

    if bullet_points:
        # 整体包装为 itemize 环境
        items = "\n".join(f"  \\item {line}" for line in lines)
        return "\\begin{itemize}\n" + items + "\n\\end{itemize}"
    else:
        # 用 \\ 连接各行
        return " \\\\\n".join(lines)


def _render_preamble() -> str:
    """返回 LaTeX 导言区。"""
    return r"""\documentclass[11pt,a4paper]{article}

% ---- 中文支持 ----
\usepackage[UTF8]{ctex}

% ---- 页面边距 ----
\usepackage[margin=2cm]{geometry}

% ---- 颜色 ----
\usepackage[table,dvipsnames]{xcolor}
\definecolor{sectioncolor}{HTML}{365F91}

% ---- 图片 ----
\usepackage{graphicx}

% ---- 标题格式 ----
\usepackage{titlesec}
\titleformat{\section}
  {\Large\bfseries\color{sectioncolor}}
  {}{0em}{}[\titlerule]

% ---- 列表格式 ----
\usepackage{enumitem}
\setlist{nosep,leftmargin=*}

% ---- 宏定义 ----
\newcommand{\cvitemheader}[2]{%
  \makebox[0.68\textwidth][l]{\textbf{#1}}%
  \makebox[0.32\textwidth][r]{\small\textit{#2}}%
}
"""


def _render_personal_info(block: dict) -> str:
    """渲染个人信息区：姓名居中加粗 + 联系方式居中 + 照片右侧。"""
    info = _get_field(block, "personalInfo", "personal_info", default={})
    name = _escape_latex(_personal_field(info, "name", default="未填写"))
    phone = _escape_latex(_personal_field(info, "phone", default=""))
    email = _escape_latex(_personal_field(info, "email", default=""))
    location = _escape_latex(_personal_field(info, "location", default=""))
    photo_path = _personal_field(info, "photoUrl", "photo_url", default="")

    # 联系方式行
    contact_parts = []
    if phone:
        contact_parts.append(phone)
    if email:
        contact_parts.append(email)
    if location:
        contact_parts.append(location)
    contact_str = r" $|$ ".join(contact_parts)

    # 照片路径转绝对路径
    photo_abs = ""
    if photo_path:
        # photo_url 是 /api/resumes/{id}/photo 格式，需要转为本地文件路径
        import re
        m = re.search(r"/resumes/(.+?)/photo", photo_path)
        if m:
            rid = m.group(1)
            for p in DATA_DIR.glob(f"{rid}_photo.*"):
                photo_abs = str(p.resolve()).replace("\\", "/")
                break

    lines = []

    if photo_abs:
        # 左右布局：左侧个人信息，右侧照片
        lines.append(r"\begin{minipage}[t]{0.68\textwidth}")
        lines.append(r"\begin{center}")
        lines.append(r"{\Huge\bfseries " + name + r"\par}")
        lines.append(r"\vspace{0.4cm}")
        if contact_str:
            lines.append(r"{\normalsize " + contact_str + r"\par}")
        lines.append(r"\end{center}")
        lines.append(r"\end{minipage}")
        lines.append(r"\hfill")
        lines.append(r"\begin{minipage}[t]{0.28\textwidth}")
        lines.append(r"\flushright")
        lines.append(r"\includegraphics[width=3cm,height=3.5cm,keepaspectratio]{" + photo_abs + "}")
        lines.append(r"\end{minipage}")
    else:
        lines.append(r"\begin{center}")
        lines.append(r"{\Huge\bfseries " + name + r"\par}")
        lines.append(r"\vspace{0.4cm}")
        if contact_str:
            lines.append(r"{\normalsize " + contact_str + r"\par}")
        lines.append(r"\end{center}")

    lines.append(r"\vspace{0.5cm}")
    return "\n".join(lines)


def _render_content_block(block: dict) -> str:
    """渲染单个正文块。"""
    content = _get_field(block, "content", default={})
    spans = _content_field(content, "spans", default=[])
    time_span = _content_field(content, "timeSpan", "time_span", default="")
    bullet_points = _content_field(content, "bulletPoints", "bullet_points", default=False)

    if not spans:
        return r"\vspace{5pt}" + "\n"

    body_latex = _spans_to_latex(spans, bullet_points)
    if not body_latex:
        return r"\vspace{5pt}" + "\n"

    lines = body_latex.strip().split("\n")

    if time_span:
        # 第一行用 \cvitemheader，其余行紧跟
        first_line = lines[0].strip().rstrip("\\\\").strip()
        # 如果第一行是 \begin{itemize}（即整个块被包在 itemize 里）
        if first_line.startswith("\\begin{itemize}"):
            # itemize 模式下做不了 cvitemheader，直接把时间跨度放在前面
            time_str = _escape_latex(time_span)
            result = [r"\cvitemheader{" + time_str + r"}{}"]
            result.append(r"\vspace{3pt}")
            result.append(body_latex.strip())
            return "\n".join(result) + "\n"

        rest_lines = lines[1:]
        time_str = _escape_latex(time_span)
        result = [r"\cvitemheader{" + first_line + r"}{" + time_str + r"}"]
        if rest_lines:
            result.append("\n".join(rest_lines))
        return "\n".join(result) + "\n"
    else:
        return body_latex.strip() + "\n"


def _render_section(group: SectionGroup) -> str:
    """渲染一个 section 组：标题 + 多个正文块。"""
    cat = _escape_latex(group.category)
    lines = [r"\section{" + cat + r"}", ""]

    for i, b in enumerate(group.blocks):
        if i > 0:
            lines.append(r"\vspace{5pt}")
        lines.append(_render_content_block(b))

    return "\n".join(lines)


def generate_latex(resume_data: dict) -> str:
    """主入口：将简历数据转换为完整 LaTeX 源码。

    Args:
        resume_data: 包含 blocks 和 connections 的简历 JSON dict

    Returns:
        完整的 .tex 文件内容字符串
    """
    blocks = resume_data.get("blocks", [])
    connections = resume_data.get("connections", [])

    # 1. 排序
    sorted_blocks = _sort_blocks(blocks, connections)

    # 2. 分离个人信息块和正文块
    personal_block = None
    for b in sorted_blocks:
        if b.get("type") == "personal_info":
            personal_block = b
            break

    # 3. 分组
    sections = _group_sections(sorted_blocks)

    # 4. 组装 LaTeX
    parts: list[str] = []

    # 导言区
    parts.append(_render_preamble())

    # 文档开始
    parts.append(r"\begin{document}")

    # 个人信息
    if personal_block:
        parts.append(_render_personal_info(personal_block))

    # 正文 sections
    for sec in sections:
        parts.append(_render_section(sec))

    # 文档结束
    parts.append(r"\end{document}")

    return "\n\n".join(parts)
