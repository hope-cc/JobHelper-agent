"""投递进度管理 API 路由。"""

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from src.api import job_storage

job_router = APIRouter()

VALID_STATUSES = ("简历已投递", "评估中", "Offer", "已拒绝")
DATE_RE = r"^\d{4}-\d{2}-\d{2}$"

import re


class JobRecordBody(BaseModel):
    """单条投递记录（不含 id，id 由服务端生成）。"""

    company: str
    position: str
    industry: str = ""
    applied_at: str
    status: str
    next_step: str = ""
    remark: str = ""

    @field_validator("company", "position")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("不能为空")
        return v.strip()

    @field_validator("applied_at")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        if not re.match(DATE_RE, v):
            raise ValueError("日期格式须为 YYYY-MM-DD")
        return v

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"状态必须是 {VALID_STATUSES} 之一")
        return v


@job_router.get("/jobs")
async def list_jobs():
    """列出全部投递记录。"""
    return {"jobs": job_storage.load()}


@job_router.post("/jobs")
async def create_job(body: JobRecordBody):
    """新增一条投递记录，返回含 id 的完整记录。"""
    record = body.model_dump()
    record["id"] = str(uuid4())
    records = job_storage.load()
    records.append(record)
    job_storage.save(records)
    return record


@job_router.put("/jobs/{job_id}")
async def update_job(job_id: str, body: JobRecordBody):
    """按 id 更新一条投递记录，id 不存在返回 404。"""
    records = job_storage.load()
    for i, rec in enumerate(records):
        if rec.get("id") == job_id:
            new_record = body.model_dump()
            new_record["id"] = job_id
            records[i] = new_record
            job_storage.save(records)
            return new_record
    raise HTTPException(status_code=404, detail="投递记录不存在")