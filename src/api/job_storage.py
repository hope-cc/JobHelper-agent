"""投递进度 JSON 文件存储。

全部投递记录保存在 data/jobs.json，单一 JSON 数组，整表覆写保存。
"""

import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "jobs.json"


def _ensure_dir() -> None:
    """确保存储目录存在。"""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


def load() -> list:
    """读取全部投递记录。文件不存在返回空列表。

    旧记录可能缺 `industry` 字段，返回前统一补齐为空字符串，
    保证调用方拿到的每条记录字段完整。
    """
    if not DATA_FILE.exists():
        return []
    records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    for rec in records:
        rec.setdefault("industry", "")
    return records


def save(records: list) -> None:
    """覆写全部投递记录。"""
    _ensure_dir()
    DATA_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )