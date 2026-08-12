"""LaTeX 生成器与简历 id 时间化的单元测试。"""

import re

from src.latex.generator import (
    _build_paragraphs,
    _build_lines_with_bold,
    _escape_latex,
    _normalize_time,
    _partition_block,
    generate_latex,
)
from src.api import resume_storage as rs


# ---- 时间归一化 ----

def test_normalize_time_hyphen():
    assert _normalize_time("2020.09-2024.06") == "2020.09 -- 2024.06"


def test_normalize_time_spaced_hyphen():
    assert _normalize_time("2025.06 - 2026.04") == "2025.06 -- 2026.04"


def test_normalize_time_endash():
    assert _normalize_time("2024.09 – 2027.06") == "2024.09 -- 2027.06"


def test_normalize_time_already_normalized():
    assert _normalize_time("2020.09 -- 2024.06") == "2020.09 -- 2024.06"


def test_normalize_time_plain():
    assert _normalize_time("至今") == "至今"


# ---- 转义（单遍替换回归） ----

def test_escape_percent_no_double_escape():
    # 10% 应转成 10\%，而不是把 \ 再转义成 \textbackslash{}
    assert _escape_latex("前 10%") == r"前 10\%"


def test_escape_literal_backslash_percent():
    # 作者已写 \% 时，\ 需转义、% 也需转义，且互不干扰
    assert _escape_latex(r"10\%") == r"10\textbackslash{}\%"


def test_escape_common_chars():
    assert _escape_latex("a_b{c}&d~e^f#g$h") == (
        r"a\_b\{c\}\&d\textasciitilde{}e\^{}f\#g\$h"
    )


# ---- 行构建与分块 ----

def _education_block():
    return {
        "type": "content",
        "content": {
            "category": "教育经历",
            "timeSpan": "2020.09-2024.06",
            "spans": [
                {"text": "广东工业大学", "bold": True},
                {"text": "    本科    自动化学院    自动化类", "bold": False},
                {"text": "\n", "bold": False},
                {"text": "•GPA: 3.8/5.0 (前 10%) ", "bold": False},
                {"text": "\n", "bold": False},
                {"text": "•数学建模竞赛省赛一等奖", "bold": False},
            ],
        },
    }


def _project_block():
    return {
        "type": "content",
        "content": {
            "category": "项目经历",
            "timeSpan": "2025.06 - 2026.04",
            "spans": [
                {"text": "研究生课题：xxx", "bold": True},
                {"text": "\n", "bold": False},
                {"text": "项目目标", "bold": True},
                {"text": "：在无信号灯交叉口仿真环境中规划轨迹。", "bold": False},
                {"text": "\n", "bold": False},
                {"text": "• ", "bold": False},
                {"text": "\n", "bold": False},
                {"text": "核心算法设计：", "bold": True},
                {"text": "设计多智能体PPO框架；引入注意力机制\n优化决策网络。", "bold": False},
                {"text": "\n", "bold": False},
                {"text": "• ", "bold": False},
                {"text": "\n", "bold": False},
                {"text": "多进程训练：", "bold": True},
                {"text": "设计并行训练框架，提速3倍。", "bold": False},
            ],
        },
    }


def _skills_block():
    return {
        "type": "content",
        "content": {
            "category": "专业技能",
            "timeSpan": "",
            "spans": [
                {"text": "• 熟悉Python，掌握Numpy。", "bold": False},
                {"text": "\n", "bold": False},
                {"text": "• 熟悉C++，面向对象、STL。", "bold": False},
            ],
        },
    }


def _personal_block():
    return {
        "type": "personal_info",
        "personalInfo": {
            "name": "廖梓希",
            "phone": "18928733892",
            "email": "cc@163.com",
            "location": "广州",
            "photoUrl": None,
        },
    }


def test_partition_block_project():
    lines = _build_lines_with_bold(_project_block()["content"]["spans"])
    head, bullets = _partition_block(lines)
    # 标题行 + 一个段落
    assert head[0].startswith(r"\textbf{研究生课题：xxx}")
    assert "项目目标" in head[1]
    # 两个列表项，且列表项内部软换行被折叠为空格
    assert len(bullets) == 2
    assert "注意力机制 优化决策网络" in bullets[0]


def test_build_paragraphs_merges_soft_wrap():
    paras = _build_paragraphs([r"\textbf{项目目标}：第一行", "第二行续写", r"\textbf{技术栈}：Python"])
    assert paras == [r"\textbf{项目目标}：第一行 第二行续写", r"\textbf{技术栈}：Python"]


# ---- generate_latex 端到端（统一布局） ----

def test_generate_latex_unified_layout():
    data = {
        "blocks": [_personal_block(), _education_block(), _project_block(), _skills_block()],
        "connections": [],
    }
    tex = generate_latex(data)

    # 导言区与宏
    assert "\\documentclass[10pt, a4paper]{ctexart}" in tex
    assert "left=1.5cm" in tex
    assert "\\newcommand{\\cvsection}" in tex

    # 章节标题
    assert r"\cvsection{\textcolor[HTML]{365F91}{教育经历}}" in tex
    assert r"\cvsection{\textcolor[HTML]{365F91}{专业技能}}" in tex

    # 无字面圆点
    assert "•" not in tex

    # 教育经历：仅学校加粗，时间右对齐，转义正确
    assert r"\noindent \textbf{广东工业大学}    本科    自动化学院    自动化类 \hfill 2020.09 -- 2024.06\par" in tex
    assert r"10\%" in tex

    # 项目经历：段落合并 + 列表项
    assert r"\noindent \textbf{项目目标}：在无信号灯交叉口仿真环境中规划轨迹。\par" in tex
    assert r"\item \textbf{核心算法设计：}设计多智能体PPO框架；引入注意力机制 优化决策网络。" in tex
    assert r"\item \textbf{多进程训练：}设计并行训练框架，提速3倍。" in tex

    # 专业技能：纯 itemize，无标题
    assert "专业技能" in tex
    assert r"\item 熟悉Python，掌握Numpy。" in tex

    # 头部：居中姓名 + tabular 联系方式（列定义用 \textbar 保证管道符在各引擎下正确渲染）
    assert r"{\huge \bfseries 廖梓希} \\[1.5ex]" in tex
    assert r"\begin{tabular}{@{\hspace{0pt}}l @{\quad \textbar \quad} l @{\quad \textbar \quad} l}" in tex
    assert r"手机号：18928733892 & 邮箱：cc@163.com & 现居地：广州" in tex
    assert "\\includegraphics" not in tex


def test_generate_latex_with_photo_by_resume_id(monkeypatch, tmp_path):
    from src.latex import generator as gen

    monkeypatch.setattr(gen, "DATA_DIR", tmp_path)
    rid = "CV-20260812-000001"
    # 照片文件存在但 JSON photoUrl 为 null（当前真实数据的形态）
    tmp_path.joinpath(f"{rid}_photo.jpg").write_bytes(b"fake-jpeg")

    data = {
        "id": rid,
        "blocks": [_personal_block()],
        "connections": [],
    }
    tex = gen.generate_latex(data)
    # 照片渲染在个人信息栏最右侧（参照 example.tex）
    assert "\\includegraphics" in tex
    assert "\\raisebox{-\\height}" in tex
    assert "\\vspace{-4cm}" in tex
    assert f"{rid}_photo.jpg" in tex


def test_generate_latex_photo_absent_without_file(monkeypatch, tmp_path):
    from src.latex import generator as gen

    monkeypatch.setattr(gen, "DATA_DIR", tmp_path)
    data = {
        "id": "no-such-resume",
        "blocks": [_personal_block()],
        "connections": [],
    }
    tex = gen.generate_latex(data)
    assert "\\includegraphics" not in tex


def test_generate_latex_real_data_smoke():
    from pathlib import Path

    fp = Path(__file__).resolve().parent.parent / "data" / "CV" / "ab64e6f5beb2.json"
    if not fp.exists():
        return
    import json

    data = json.loads(fp.read_text(encoding="utf-8"))
    tex = generate_latex(data)
    assert "ctexart" in tex
    assert "•" not in tex
    assert "\\item" in tex


# ---- 简历 id 时间化 ----

def test_resume_id_format(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "DATA_DIR", tmp_path)
    rid = rs._generate_resume_id()
    assert re.match(r"^CV-\d{8}-\d{6}$", rid)


def test_resume_id_collision(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "DATA_DIR", tmp_path)
    a = rs._generate_resume_id()
    tmp_path.joinpath(a + ".json").write_text("{}", encoding="utf-8")
    b = rs._generate_resume_id()
    assert b == a + "-2"
