"""getPersonalInfo 工具。

读取本地持久化的个人信息（data/personal/profile.json），
将被用户标记为敏感的基本信息字段值以 "***" 替换后返回整份信息。
持久化文件中的原始值保持不变。
"""

import json

from pydantic import BaseModel

from src.api import profile_storage
from src.tools import tool


class Params(BaseModel):
    """getPersonalInfo 无参数。"""


@tool(
    name="getPersonalInfo",
    description=(
        "从本地持久化存储中获取用户预先设置的个人信息，用于投递简历填写表单。"
        "无需参数。被用户标记为敏感的基本信息字段（如手机、证件号）会以 *** 替换。"
    ),
)
async def getPersonalInfo(params: Params) -> str:
    data = profile_storage.load()
    if data is None:
        return "尚未保存个人信息，请先在「个人信息管理」页面填写并保存后再调用。"

    mask_keys = data.pop("masked_basic_fields", [])
    basic = data.get("basic_info", {})
    for key in mask_keys:
        if basic.get(key):
            basic[key] = "***"
    return json.dumps(data, ensure_ascii=False, indent=2)
