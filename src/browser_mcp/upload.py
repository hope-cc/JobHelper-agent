"""简历上传辅助。

扫描 `data/CV` 下的简历 PDF、识别上传控件、处理多份简历选择，
并调用 MCP `browser_upload_file` 上传后等待网页解析。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from src.browser_mcp.client import call_tool
from src.browser_mcp.fill import is_upload_candidate

DATA_CV_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "CV"

# 上传后等待网页解析简历的时长（秒）
PARSE_WAIT_SECONDS = 5


@dataclass
class ResumeChoice:
    """简历选择结果。"""

    action: str  # upload / ask / error
    path: Path | None = None
    message: str = ""
    candidates: list[Path] = field(default_factory=list)


def list_resume_pdfs() -> list[Path]:
    """返回 data/CV 下的 PDF 简历，按修改时间倒序（最新在前）。"""
    if not DATA_CV_DIR.exists():
        return []
    return sorted(
        DATA_CV_DIR.glob("*.pdf"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def find_upload_control(elements: list[dict]) -> dict | None:
    """从快照元素中找首个上传入口控件。"""
    for el in elements:
        if is_upload_candidate(el):
            return el
    return None


def _candidates_text(pdfs: list[Path]) -> str:
    return "\n".join(f"{i + 1}. {p.name}" for i, p in enumerate(pdfs))


def resolve_resume(spec: str) -> ResumeChoice:
    """解析简历选择。

    - spec 为空：0 份 → error；1 份 → upload；多份 → ask（返回候选清单）
    - spec 为序号（1 起）或文件名：匹配到 → upload；否则 → error
    """
    pdfs = list_resume_pdfs()
    if not pdfs:
        return ResumeChoice(
            action="error",
            message="data/CV 目录下没有简历 PDF，请先上传一份简历。",
        )

    spec = (spec or "").strip()
    if not spec:
        if len(pdfs) == 1:
            return ResumeChoice(action="upload", path=pdfs[0])
        return ResumeChoice(
            action="ask",
            candidates=pdfs,
            message=(
                f"data/CV 下检测到 {len(pdfs)} 份简历：\n{_candidates_text(pdfs)}\n"
                f"请告诉我要用哪一份（回复序号或文件名）。"
            ),
        )

    if spec.isdigit():
        idx = int(spec) - 1
        if 0 <= idx < len(pdfs):
            return ResumeChoice(action="upload", path=pdfs[idx])
        return ResumeChoice(
            action="error",
            message=f"序号 {spec} 超出范围（data/CV 共 {len(pdfs)} 份简历）。\n{_candidates_text(pdfs)}",
        )

    for p in pdfs:
        if p.name == spec or p.stem == spec:
            return ResumeChoice(action="upload", path=p)
    return ResumeChoice(
        action="error",
        message=f"在 data/CV 中未找到「{spec}」。现有简历：\n{_candidates_text(pdfs)}",
    )


def _flip_drive_case(path: str) -> str:
    """翻转路径盘符大小写（Playwright MCP 的 allowed roots 比较区分大小写）。"""
    if len(path) >= 2 and path[1] == ":":
        return path[0].swapcase() + path[1:]
    return path


async def upload_and_wait(ref: str, path: Path) -> tuple[str, bool]:
    """点击上传控件打开文件选择器，再上传简历，等待网页解析后返回 (内容, is_error)。

    服务器 allowed roots 的盘符大小写随启动方式而异（run.py 启动为小写、手动 npx 启动为大写），
    因此遇到 "File access denied" 时直接再次调用 browser_file_upload（文件选择器仍处于打开状态），
    翻转盘符大小写重试一次。
    """
    click_text, click_err = await call_tool("browser_click", {"target": ref})
    if click_err:
        return click_text, click_err

    candidates = [str(path), _flip_drive_case(str(path))]
    last_text, last_err = "", True
    for cand in candidates:
        text, err = await call_tool("browser_file_upload", {"paths": [cand]})
        if err and "File access denied" in text:
            last_text, last_err = text, err
            continue  # 盘符大小写不匹配，文件选择器仍在，换大小写重试
        await asyncio.sleep(PARSE_WAIT_SECONDS)
        return text, err
    await asyncio.sleep(PARSE_WAIT_SECONDS)
    return last_text, last_err
