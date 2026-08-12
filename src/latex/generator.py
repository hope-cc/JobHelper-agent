"""LaTeX 代码生成器。

将简历 JSON 数据（blocks + connections）转换为完整的 LaTeX 源码，
排版风格与 example.tex 保持一致（ctexart、cvsection、统一布局）。
"""

import re
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


# ---- 排序与分组（沿用现有逻辑） ----

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


# ---- LaTeX 转义 ----

_ESCAPE_TABLE = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\^{}",
}

_ESCAPE_RE = re.compile(r"[\\&%$#_{}~^]")


def _escape_latex(text: str) -> str:
    """转义 LaTeX 特殊字符（单遍替换，避免替换结果被二次转义）。"""
    return _ESCAPE_RE.sub(lambda m: _ESCAPE_TABLE[m.group()], text)


# ---- 导言区与常量 ----

_ITEMIZE_OPTS = "leftmargin=1.5em, itemsep=0pt, parsep=0pt, topsep=0ex"

_PREAMBLE = r"""\documentclass[10pt, a4paper]{ctexart}

% 设置页面边距
\usepackage[left=1.5cm, right=1.5cm, top=1.5cm, bottom=1.5cm]{geometry}
% 用于插入图片
\usepackage{graphicx}
% 用于自定义列表间距
\usepackage{enumitem}
% 用于自定义颜色（打码块）
\usepackage{xcolor}
% 用于技能部分的表格排版
\usepackage{tabularx}
\usepackage[hidelinks]{hyperref}
% 禁用页码
\pagestyle{empty}
% 取消段首缩进
\setlength{\parindent}{0pt}

% ==================== 自定义宏命令 ====================
% 自定义模块标题命令 (带有下划线)
\newcommand{\cvsection}[1]{
    \vspace{2ex}
    {\large\bfseries #1}
    \vspace{0.5ex}
    \hrule height 1pt
    \vspace{1.5ex}
}

% 自定义项目标题行 (左侧加粗，右侧时间)
\newcommand{\cvitemheader}[2]{
    {\bfseries #1} \hfill #2 \par
    \vspace{0.5ex}
}

% 自定义项目副标题行 (左侧普通文本，右侧地点)
\newcommand{\cvsubitem}[2]{
    {#1} \hfill #2 \par
    \vspace{0.5ex}
}"""


# ---- 时间归一化 ----

def _normalize_time(ts: str) -> str:
    """将日期区间分隔符规范化为 LaTeX 的 en-dash（--）。"""
    return re.sub(r"(?<=\d)\s*[–-]\s*(?=\d)", " -- ", ts)


# ---- 行构建与分块 ----

def _build_lines_with_bold(spans: list[dict]) -> list[str]:
    """逐 span 构建带加粗标记的行。

    span 文本转义后若 bold 则包 \\textbf{}，按 \\n 拆行。
    返回 strip 后的非空行列表，但保留恰好为 "•" 的行。
    """
    lines: list[str] = [""]
    for s in spans:
        text = _escape_latex(s.get("text", ""))
        parts = text.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                lines.append("")
            if part:
                if s.get("bold"):
                    lines[-1] += r"\textbf{" + part + "}"
                else:
                    lines[-1] += part

    result: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            continue
        if stripped == "•":
            result.append("•")
        else:
            result.append(stripped)
    return result


def _build_paragraphs(head_lines: list[str]) -> list[str]:
    """将标题之后的若干行聚合为段落列表。

    以「行首为 \\textbf{」作为新段落起点；普通行视为上一段落的续行（空格连接），
    从而把段落内部的软换行（\\n）合并回同一段落。
    """
    paragraphs: list[str] = []
    current: str | None = None
    for ln in head_lines:
        if current is None or ln.startswith(r"\textbf{"):
            if current is not None:
                paragraphs.append(current)
            current = ln
        else:
            current += " " + ln
    if current is not None:
        paragraphs.append(current)
    return paragraphs


def _partition_block(lines: list[str]) -> tuple[list[str], list[str]]:
    """将行划分为 (非列表区, 列表项列表)。

    「行首为 •」为列表边界；首个 • 行之前为非列表区；
    每个 • 行起至下一个 • 行之间的内容合并为一个列表项（内部行用空格连接）。
    """
    head: list[str] = []
    bullets: list[str] = []
    current: list[str] = []
    in_bullets = False

    for ln in lines:
        if ln.startswith("•"):
            if current:
                bullets.append(" ".join(current).strip())
            in_bullets = True
            rest = ln[1:].strip()
            current = [rest] if rest else []
        elif in_bullets:
            current.append(ln)
        else:
            head.append(ln)

    if current:
        bullets.append(" ".join(current).strip())

    return head, bullets


# ---- 照片解析 ----

def _resolve_photo_path(resume_id: str = "", photo_url: str = "") -> str:
    """解析简历照片的本地绝对路径。

    优先按 resume_id 在 data/CV 下直接查找照片文件（{id}_photo.*），
    找不到时再尝试从 photoUrl（/api/resumes/{id}/photo）提取 id 查找。
    """
    def _glob(rid: str) -> str:
        for p in DATA_DIR.glob(f"{rid}_photo.*"):
            return str(p.resolve()).replace("\\", "/")
        return ""

    # resume_id 可能是空或含 glob 特殊字符的测试数据，先做白名单校验
    if resume_id and re.fullmatch(r"[A-Za-z0-9-]+", resume_id):
        found = _glob(resume_id)
        if found:
            return found

    if photo_url:
        m = re.search(r"/resumes/(.+?)/photo", photo_url)
        rid = m.group(1) if m else None
        if rid:
            found = _glob(rid)
            if found:
                return found

    return ""


# ---- 区块渲染 ----

def _render_personal_info(block: dict, resume_id: str = "") -> str:
    """渲染头部：居中姓名 + tabular 联系方式 + 右上角照片。

    照片位置参照 example.tex：置于个人信息栏最右侧，用负间距上移到姓名区右侧。
    """
    info = _get_field(block, "personalInfo", "personal_info", default={})
    name = _escape_latex(_personal_field(info, "name", default="未填写"))
    phone = _escape_latex(_personal_field(info, "phone", default=""))
    email = _escape_latex(_personal_field(info, "email", default=""))
    location = _escape_latex(_personal_field(info, "location", default=""))
    photo_url = _personal_field(info, "photoUrl", "photo_url", default="")

    fields = []
    if phone:
        fields.append(("手机号：", phone))
    if email:
        fields.append(("邮箱：", email))
    if location:
        fields.append(("现居地：", location))

    lines = [r"\begin{center}"]
    lines.append(r"{\huge \bfseries " + name + r"} \\[1.5ex]")
    if fields:
        # 分隔符用 \textbar 而非字面 |：pdflatex(OT1) 下 | 会渲染成 em-dash
        cols = r"@{\hspace{0pt}}l" + r" @{\quad \textbar \quad} l" * (len(fields) - 1)
        lines.append(r"\begin{tabular}{" + cols + "}")
        lines.append("    " + " & ".join(label + val for label, val in fields))
        lines.append(r"\end{tabular}")
    lines.append(r"\end{center}")

    photo_abs = _resolve_photo_path(resume_id, photo_url)
    if photo_abs:
        lines.append("")
        lines.append(r"\vspace{-4cm}")
        lines.append(r"\hfill")
        lines.append(
            r"\raisebox{-\height}{\includegraphics[width=2.5cm,height=3.5cm]{"
            + photo_abs
            + r"}}"
        )

    return "\n".join(lines)


def _render_content_block(block: dict) -> str:
    """渲染单个正文块：标题行 + 段落 + 列表（统一布局）。

    - 标题行 = 非列表区第一行，保留 spans 加粗，时间 \\hfill 右对齐
    - 段落 = 非列表区其余行
    - 列表 = 所有 • 列表项，单个 itemize 环境
    """
    content = _get_field(block, "content", default={})
    spans = _content_field(content, "spans", default=[])
    time_span = _content_field(content, "timeSpan", "time_span", default="")

    if not spans:
        return ""

    lines = _build_lines_with_bold(spans)
    if not lines:
        return ""

    head, bullets = _partition_block(lines)
    title = head[0] if head else None
    paragraphs = _build_paragraphs(head[1:])

    parts: list[str] = []

    if title:
        time_str = _escape_latex(_normalize_time(time_span)) if time_span else ""
        if time_str:
            parts.append(r"\noindent " + title + r" \hfill " + time_str + r"\par")
        else:
            parts.append(r"\noindent " + title + r"\par")
        if paragraphs:
            parts.append(r"\vspace{0.5ex}")

    for p in paragraphs:
        parts.append(r"\noindent " + p + r"\par")

    if bullets:
        parts.append(r"\begin{itemize}[" + _ITEMIZE_OPTS + "]")
        parts.extend(r"  \item " + b for b in bullets)
        parts.append(r"\end{itemize}")

    return "\n".join(parts) + "\n"


def _render_section(group: SectionGroup) -> str:
    """渲染一个 section 组：cvsection 标题 + 多个正文块。"""
    cat = _escape_latex(group.category)
    lines = [r"\cvsection{\textcolor[HTML]{365F91}{" + cat + r"}}", ""]

    rendered = 0
    for b in group.blocks:
        block_latex = _render_content_block(b)
        if not block_latex:
            continue
        if rendered > 0:
            lines.append(r"\vspace{5pt}")
        lines.append(block_latex.strip())
        rendered += 1

    return "\n".join(lines)


# ---- 主入口 ----

def generate_latex(resume_data: dict) -> str:
    """主入口：将简历数据转换为与 example.tex 风格一致的 LaTeX 源码。

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
    parts: list[str] = [_PREAMBLE]
    parts.append(r"\begin{document}")

    if personal_block:
        parts.append(_render_personal_info(personal_block, resume_data.get("id", "")))

    for sec in sections:
        parts.append(_render_section(sec))

    parts.append(r"\end{document}")

    return "\n\n".join(parts)
