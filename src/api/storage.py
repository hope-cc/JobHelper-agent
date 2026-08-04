"""JSON 文件会话存储。

每个会话一个 JSON 文件，存储在 data/conversations/ 目录下。
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "conversations"


def _ensure_dir() -> None:
    """确保存储目录存在。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _file_path(conversation_id: str) -> Path:
    """获取会话 JSON 文件路径。"""
    return DATA_DIR / f"{conversation_id}.json"


def list_conversations() -> list[dict]:
    """列出所有会话摘要（不含 messages），按创建时间倒序。"""
    _ensure_dir()
    conversations: list[dict] = []
    for f in sorted(DATA_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            conversations.append({
                "id": data["id"],
                "title": data["title"],
                "created_at": data["created_at"],
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return conversations


def get_conversation(conversation_id: str) -> dict | None:
    """获取完整会话（含 messages）。不存在返回 None。"""
    fp = _file_path(conversation_id)
    if not fp.exists():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def create_conversation() -> dict:
    """创建新会话，返回完整会话对象。"""
    _ensure_dir()
    now = datetime.now(timezone.utc).isoformat()
    conv = {
        "id": uuid.uuid4().hex[:12],
        "title": "新对话",
        "created_at": now,
        "messages": [],
    }
    _file_path(conv["id"]).write_text(json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8")
    return conv


def add_message(conversation_id: str, message: dict) -> None:
    """向会话追加一条消息。message 格式: {"role": "...", "content": "..."}"""
    fp = _file_path(conversation_id)
    if not fp.exists():
        raise FileNotFoundError(f"会话不存在: {conversation_id}")
    data = json.loads(fp.read_text(encoding="utf-8"))
    data["messages"].append(message)
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_title(conversation_id: str, title: str) -> None:
    """更新会话标题。"""
    fp = _file_path(conversation_id)
    if not fp.exists():
        raise FileNotFoundError(f"会话不存在: {conversation_id}")
    data = json.loads(fp.read_text(encoding="utf-8"))
    data["title"] = title
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
