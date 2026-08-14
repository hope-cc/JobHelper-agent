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
        "basic_fields_schema": [
            {"key": "name", "label": "姓名", "type": "text"},
            {"key": "phone", "label": "手机", "type": "text"},
            {"key": "email", "label": "邮箱", "type": "text"},
            {
                "key": "gender",
                "label": "性别",
                "type": "select",
                "options": ["男", "女", "其他"],
            },
            {"key": "age", "label": "年龄", "type": "text"},
            {"key": "location", "label": "所在地点", "type": "text"},
            {
                "key": "id_type",
                "label": "证件类型",
                "type": "select",
                "options": ["身份证", "护照", "港澳通行证", "台湾居民来往大陆通行证", "其他"],
            },
            {"key": "id_number", "label": "证件号码", "type": "text"},
            {"key": "id_valid_until", "label": "有效期", "type": "text"},
            {"key": "hometown", "label": "家乡", "type": "text"},
        ],
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
        "award": [],
        "language": [],
        "self_evaluation": "",
        "masked_basic_fields": [],
    }


def load() -> dict | None:
    """读取整份个人信息。文件不存在返回 None。

    实习/项目分区已移除，这里剥离历史遗留数据，保证页面与 LLM 工具都读不到。
    """
    if not PROFILE_FILE.exists():
        return None
    data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    data.pop("internship", None)
    data.pop("project", None)
    return data


def save(data: dict) -> None:
    """覆写整份个人信息。"""
    _ensure_dir()
    PROFILE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
