"""简历管理 API 路由。"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from src.api import resume_storage
from src.latex import generate_latex, compile_latex

resume_router = APIRouter()


class UpdateResumeBody(BaseModel):
    name: str
    created_at: str
    updated_at: str
    blocks: list
    connections: list


@resume_router.get("/resumes")
async def list_resumes():
    """列出所有简历摘要。"""
    return resume_storage.list_resumes()


@resume_router.post("/resumes")
async def create_resume():
    """创建新简历，返回完整对象。"""
    data = resume_storage._default_resume()
    resume_storage.save_resume(data["id"], data)
    return data


@resume_router.get("/resumes/{resume_id}")
async def get_resume(resume_id: str):
    """获取简历完整数据。"""
    data = resume_storage.load_resume(resume_id)
    if data is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    return data


@resume_router.put("/resumes/{resume_id}")
async def update_resume(resume_id: str, body: UpdateResumeBody):
    """全量更新简历。"""
    data = resume_storage.load_resume(resume_id)
    if data is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    new_data = body.model_dump()
    new_data["id"] = resume_id
    resume_storage.save_resume(resume_id, new_data)
    return Response(status_code=200)


@resume_router.delete("/resumes/{resume_id}")
async def delete_resume(resume_id: str):
    """删除简历及关联照片。"""
    resume_storage.delete_resume(resume_id)
    return Response(status_code=204)


@resume_router.post("/resumes/{resume_id}/copy")
async def copy_resume(resume_id: str):
    """复制简历，返回新简历对象。"""
    src = resume_storage.load_resume(resume_id)
    if src is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    new_data = resume_storage._default_resume(name=f"{src['name']} (副本)")
    new_data["blocks"] = src.get("blocks", [])
    new_data["connections"] = src.get("connections", [])
    resume_storage.save_resume(new_data["id"], new_data)

    # 复制照片
    photo_path = resume_storage.get_photo_path(resume_id)
    if photo_path:
        import shutil
        src_photo = resume_storage.DATA_DIR.parent / photo_path
        ext = src_photo.suffix
        dst_photo = resume_storage.DATA_DIR / f"{new_data['id']}_photo{ext}"
        shutil.copy2(src_photo, dst_photo)

    return new_data


@resume_router.post("/resumes/{resume_id}/photo")
async def upload_photo(resume_id: str, file: UploadFile = File(...)):
    """上传简历照片。"""
    # 校验文件类型
    if file.content_type not in ("image/jpeg", "image/png", "image/jpg"):
        raise HTTPException(status_code=400, detail="仅支持 JPG/PNG 格式")

    # 校验文件大小
    contents = await file.read()
    max_size = 5 * 1024 * 1024  # 5MB
    if len(contents) > max_size:
        raise HTTPException(status_code=400, detail="文件大小不能超过 5MB")

    # 将读过的内容放回以便 save_photo 使用
    file.file.seek(0)

    # 确保简历存在
    data = resume_storage.load_resume(resume_id)
    if data is None:
        raise HTTPException(status_code=404, detail="简历不存在")

    relative_path = resume_storage.save_photo(resume_id, file)
    photo_url = f"/api/resumes/{resume_id}/photo"

    # 更新简历中的 photo_url
    for block in data.get("blocks", []):
        if block.get("type") == "personal_info":
            if "personal_info" not in block:
                block["personal_info"] = {}
            block["personal_info"]["photo_url"] = photo_url
    resume_storage.save_resume(resume_id, data)

    return {"photo_url": photo_url}


@resume_router.get("/resumes/{resume_id}/photo")
async def get_photo(resume_id: str):
    """获取简历照片文件。"""
    photo_path = resume_storage.get_photo_path(resume_id)
    if photo_path is None:
        raise HTTPException(status_code=404, detail="照片不存在")
    full_path = resume_storage.DATA_DIR.parent / photo_path
    return FileResponse(str(full_path))


@resume_router.post("/resumes/{resume_id}/generate")
async def generate_resume(resume_id: str):
    """生成 LaTeX 并编译为 PDF。"""
    data = resume_storage.load_resume(resume_id)
    if data is None:
        raise HTTPException(status_code=404, detail="简历不存在")

    # 1. 保存最新数据
    resume_storage.save_resume(resume_id, data)

    # 2. 生成 LaTeX 源码
    try:
        tex_content = generate_latex(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LaTeX 生成失败: {str(exc)}")

    # 3. 写入 .tex 文件
    tex_path = resume_storage.DATA_DIR / f"{resume_id}.tex"
    tex_path.write_text(tex_content, encoding="utf-8")

    # 4. 编译
    result = compile_latex(resume_id)
    if result["success"]:
        return {"success": True, "pdf_url": f"/api/resumes/{resume_id}/preview"}
    else:
        raise HTTPException(status_code=500, detail=result["error"])


@resume_router.get("/resumes/{resume_id}/preview")
async def preview_resume(resume_id: str):
    """在线预览生成的 PDF。"""
    pdf_path = resume_storage.DATA_DIR / f"{resume_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF 尚未生成，请先生成简历")
    return FileResponse(str(pdf_path), media_type="application/pdf")


@resume_router.get("/resumes/{resume_id}/download")
async def download_resume(resume_id: str):
    """下载生成的 PDF。"""
    pdf_path = resume_storage.DATA_DIR / f"{resume_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF 尚未生成，请先生成简历")

    # 用简历名称作为下载文件名
    data = resume_storage.load_resume(resume_id)
    filename = f"{data.get('name', '简历')}.pdf" if data else f"简历_{resume_id}.pdf"

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
