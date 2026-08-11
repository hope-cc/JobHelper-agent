"""个人信息 JSON 文件存储。

整份个人信息保存在 data/personal/profile.json，单份档案覆盖保存。
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "personal"
PROFILE_FILE = DATA_DIR / "profile.json"


def _ensure_dir() -> None:
    """确保存储目录存在。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def empty_profile() -> dict:
    """返回空默认的个人信息字典。"""
    return {
        "basic_info": {
            "name": "",
            "phone": "",
            "email": "",
            "gender": "",
            "age": "",
            "location": "",
            "id_type": "",
            "id_number": "",
            "id_valid_until": "",
            "hometown": "",
        },
        "education": [],
        "internship": [],
        "project": [],
        "award": [],
        "language": [],
        "self_evaluation": "",
        "masked_basic_fields": [],
    }


def load() -> dict | None:
    """读取整份个人信息。文件不存在返回 None。"""
    if not PROFILE_FILE.exists():
        return None
    return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))


def save(data: dict) -> None:
    """覆写整份个人信息。"""
    _ensure_dir()
    PROFILE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
