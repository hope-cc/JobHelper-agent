"""简历 JSON 文件存储。

每份简历一个 JSON 文件 + 可选照片，存储在 data/CV/ 目录下。
"""

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "CV"


def _ensure_dir() -> None:
    """确保存储目录存在。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _file_path(resume_id: str) -> Path:
    """获取简历 JSON 文件路径。"""
    return DATA_DIR / f"{resume_id}.json"


def _default_resume(name: str = "未命名简历") -> dict:
    """生成一个默认的空简历对象。"""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "created_at": now,
        "updated_at": now,
        "blocks": [],
        "connections": [],
    }


def list_resumes() -> list[dict]:
    """列出所有简历摘要（不含 blocks/connections），按更新时间倒序。"""
    _ensure_dir()
    resumes: list[dict] = []
    for f in sorted(DATA_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            resumes.append({
                "id": data["id"],
                "name": data["name"],
                "created_at": data["created_at"],
                "updated_at": data["updated_at"],
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return resumes


def load_resume(resume_id: str) -> dict | None:
    """加载完整简历（含 blocks、connections）。不存在返回 None。"""
    fp = _file_path(resume_id)
    if not fp.exists():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def save_resume(resume_id: str, data: dict) -> None:
    """保存简历，自动更新 updated_at。"""
    _ensure_dir()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _file_path(resume_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def delete_resume(resume_id: str) -> bool:
    """删除简历 JSON 及关联照片文件。

    文件不存在时返回 False（幂等，不抛异常）。
    """
    fp = _file_path(resume_id)
    deleted = False
    try:
        fp.unlink()
        deleted = True
    except FileNotFoundError:
        pass

    # 删除关联照片
    for photo in DATA_DIR.glob(f"{resume_id}_photo.*"):
        try:
            photo.unlink()
        except FileNotFoundError:
            pass

    return deleted


def save_photo(resume_id: str, file: UploadFile) -> str:
    """保存照片文件，返回相对路径字符串。

    保留原始扩展名，先删除旧照片。
    """
    _ensure_dir()

    # 删除旧照片
    for old in DATA_DIR.glob(f"{resume_id}_photo.*"):
        try:
            old.unlink()
        except FileNotFoundError:
            pass

    ext = Path(file.filename or "photo.jpg").suffix.lstrip(".") or "jpg"
    photo_path = DATA_DIR / f"{resume_id}_photo.{ext}"

    with open(photo_path, "wb") as f:
        f.write(file.file.read())

    return str(photo_path.relative_to(DATA_DIR.parent))


def get_photo_path(resume_id: str) -> str | None:
    """查找照片文件路径，返回相对于 data/ 的路径。不存在返回 None。"""
    for photo in DATA_DIR.glob(f"{resume_id}_photo.*"):
        return str(photo.relative_to(DATA_DIR.parent))
    return None
