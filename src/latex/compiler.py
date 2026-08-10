"""LaTeX 编译器。

在 data/CV/ 目录下调用 pdflatex 编译 .tex 文件生成 .pdf。
"""

import os
import shutil
import subprocess
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "CV"

def _find_pdflatex() -> str | None:
    """定位 pdflatex 可执行文件路径。"""
    # 1. 优先从 PATH 中查找（终端直接调用的方式）
    found = shutil.which("pdflatex")
    if found:
        return found

    # 2. 遍历常见安装路径
    candidates = [
        # 系统级 MiKTeX
        r"C:\Program Files\MiKTeX\miktex\bin\x64\pdflatex.exe",
        # 用户级 MiKTeX
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe"),
        os.path.expandvars(r"%APPDATA%\MiKTeX\miktex\bin\x64\pdflatex.exe"),
        # TeX Live
        r"C:\texlive\2025\bin\windows\pdflatex.exe",
        r"C:\texlive\2024\bin\windows\pdflatex.exe",
        r"C:\texlive\2023\bin\windows\pdflatex.exe",
        # 旧版 MikTeX
        r"C:\MiKTeX\miktex\bin\pdflatex.exe",
        # 新版 MikTeX (非 x64)
        r"C:\Program Files\MiKTeX\miktex\bin\pdflatex.exe",
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    # 3. 非标准路径：扫描多盘符下的 MiKTeX / TeX Live
    for drive in ("D", "E", "F"):
        for pattern in (
            f"**/MiKTeX*/miktex/bin/x64/pdflatex.exe",
            f"**/texlive/*/bin/windows/pdflatex.exe",
        ):
            for p in Path(f"{drive}:/").glob(pattern):
                found_path = str(p.resolve())
                if os.path.isfile(found_path):
                    return found_path

    return None


def compile_latex(resume_id: str) -> dict:
    """编译指定简历的 .tex 文件为 .pdf。

    Args:
        resume_id: 简历 ID

    Returns:
        {"success": bool, "pdf_path": str|None, "error": str|None}
    """
    tex_file = DATA_DIR / f"{resume_id}.tex"
    if not tex_file.exists():
        return {"success": False, "pdf_path": None, "error": f".tex 文件不存在: {tex_file}"}

    pdflatex = _find_pdflatex()
    if pdflatex is None:
        return {
            "success": False,
            "pdf_path": None,
            "error": (
                "未找到 pdflatex，请安装 MiKTeX 或 TeX Live，"
                "并确保其 bin 目录在系统 PATH 中。"
            ),
        }

    try:
        result = subprocess.run(
            [
                pdflatex,
                "-interaction=nonstopmode",
                "-output-directory",
                str(DATA_DIR),
                str(tex_file),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(DATA_DIR),
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "pdf_path": None, "error": "LaTeX 编译超时 (30 秒)"}

    pdf_file = DATA_DIR / f"{resume_id}.pdf"

    if not pdf_file.exists():
        # 提取关键错误信息
        error_lines = []
        for line in result.stdout.split("\n") + result.stderr.split("\n"):
            if line.startswith("!"):
                error_lines.append(line.strip())
        error_msg = "\n".join(error_lines[:5]) if error_lines else result.stdout[-500:]
        return {"success": False, "pdf_path": None, "error": f"编译失败:\n{error_msg}"}

    # 清理辅助文件
    for aux_ext in (".aux", ".log", ".out"):
        aux_file = DATA_DIR / f"{resume_id}{aux_ext}"
        try:
            aux_file.unlink()
        except FileNotFoundError:
            pass

    return {"success": True, "pdf_path": str(pdf_file), "error": None}
