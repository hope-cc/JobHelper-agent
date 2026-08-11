"""个人信息管理 API 路由。"""

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from src.api import profile_storage

profile_router = APIRouter()


class PersonalProfileBody(BaseModel):
    """整份个人信息字典，键与前端保存的结构一致。"""

    basic_info: dict
    education: list
    internship: list
    project: list
    award: list
    language: list
    self_evaluation: str
    masked_basic_fields: list[str] = []


@profile_router.get("/personal")
async def get_personal():
    """获取整份个人信息，未保存过时返回空默认结构。"""
    data = profile_storage.load()
    if data is None:
        return profile_storage.empty_profile()
    return data


@profile_router.put("/personal")
async def save_personal(body: PersonalProfileBody):
    """覆写整份个人信息到 data/personal/profile.json。"""
    profile_storage.save(body.model_dump())
    return Response(status_code=200)
