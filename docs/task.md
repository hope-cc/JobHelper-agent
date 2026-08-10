# LaTeX 生成与 PDF 导出 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/latex/__init__.py` | 导出 generate_latex, compile_latex |
| 新建 | `src/latex/generator.py` | LaTeX 代码生成 |
| 新建 | `src/latex/compiler.py` | pdflatex 编译 |
| 修改 | `src/api/resume_routes.py` | 替换 generate，新增 preview/download |
| 修改 | `frontend/src/api/resumeClient.ts` | 新增 generateResume, getPdfUrl, getDownloadUrl |
| 修改 | `frontend/src/components/EditorToolbar.tsx` | 新增预览按钮，generate 调真实 API |
| 修改 | `frontend/src/components/ResumeCard.tsx` | 下载按钮调真实 API |

## T1: LaTeX 代码生成器

**文件：** `src/latex/generator.py`
**依赖：** 无
**步骤：**
1. 实现 `_sort_blocks(blocks, connections)` — 遍历 connections 构建邻接表，从 type="personal_info" 的块开始沿链 BFS，返回按序排列的块列表。若无连线则回退到 blocks 原始顺序
2. 实现 `_group_sections(sorted_blocks)` — 遍历排序块，跳过个人信息块，连续相同 category 的正文块归入同一 SectionGroup
3. 实现 `_render_preamble()` — 返回 LaTeX 导言区字符串（article + ctex + geometry + xcolor + titlesec + enumitem + section 格式 + \cvitemheader 定义）
4. 实现 `_render_personal_info(block)` — minipage 左右布局，左侧 0.7 姓名+联系方式，右侧 0.3 照片
5. 实现 `_spans_to_latex(spans, bullet_points)` — 转换 TextSpan[] → LaTeX；bold span → `\textbf{...}`；换行 → `\\`；若 bullet_points=true 且文本含多行，包装为 `\begin{itemize}\item ...\end{itemize}`
6. 实现 `_render_content_block(block)` — 取第一行文字 + timeSpan 构造 `\cvitemheader{第一行}{timeSpan}`，剩余行紧跟；若 bulletPoints=true 整体放 itemize 内
7. 实现 `_render_section(group)` — 输出 `\section{category}` + 遍历 group.blocks 调用 `_render_content_block`，用 `\vspace{5pt}` 分隔
8. 实现 `generate_latex(resume_data)` — 组合上述：preamble + begin document + personal info + sections + end document

**验证：** 用 sample resume JSON 调用，输出合法 .tex 字符串

## T2: LaTeX 编译器

**文件：** `src/latex/compiler.py`
**依赖：** T1
**步骤：**
1. 实现 `compile_latex(resume_id)` — 在 data/CV/ 目录下执行 `pdflatex -interaction=nonstopmode {id}.tex`
2. 用 `subprocess.run` 调用，设置 `timeout=30`
3. 捕获 stdout/stderr
4. 检查 `data/CV/{id}.pdf` 是否生成
5. 清理辅助文件（.aux, .log, .out）
6. 返回 dict: `{"success": bool, "pdf_path": str | None, "error": str | None}`

**验证：** 用 T1 生成的 .tex 调用编译器，确认 .pdf 被创建

## T3: __init__.py 导出

**文件：** `src/latex/__init__.py`
**依赖：** T1, T2
**步骤：**
1. `from src.latex.generator import generate_latex`
2. `from src.latex.compiler import compile_latex`

**验证：** `from src.latex import generate_latex, compile_latex` 无 ImportError

## T4: API 路由更新

**文件：** `src/api/resume_routes.py`
**依赖：** T3
**步骤：**
1. 替换 `generate_resume` 端点逻辑：加载简历 → save_resume（保存最新数据） → generate_latex(data) → 写入 .tex → compile_latex(id) → 成功返回 `{"success": true, "pdf_url": f"/api/resumes/{id}/preview"}`，失败返回 500 + 错误信息
2. 新增 `GET /resumes/{resume_id}/preview` — 返回 PDF FileResponse，media_type="application/pdf"，inline 显示
3. 新增 `GET /resumes/{resume_id}/download` — 返回 PDF FileResponse，headers 设 Content-Disposition attachment，filename="简历名称.pdf"
4. 移除旧的 501 占位逻辑

**验证：** curl 测试三个端点
- POST generate → 200 + pdf_url
- GET preview → PDF 文件
- GET download → 下载触发

## T5: 前端 API Client 更新

**文件：** `frontend/src/api/resumeClient.ts`
**依赖：** T4
**步骤：**
1. 新增 `generateResume(id)` — POST `/api/resumes/{id}/generate`，返回 `{success, pdf_url, error?}`
2. 新增 `getPdfUrl(id)` — 返回 `/api/resumes/{id}/preview` 字符串
3. 新增 `getDownloadUrl(id)` — 返回 `/api/resumes/{id}/download` 字符串

**验证：** `npx tsc --noEmit` 无错误

## T6: EditorToolbar 更新

**文件：** `frontend/src/components/EditorToolbar.tsx`
**依赖：** T5
**步骤：**
1. 在"生成简历"按钮左侧新增"预览"按钮（蓝色 outline 样式）
2. "预览"按钮逻辑：若无 PDF 或未生成过，先调 generateResume → 成功后 window.open(getPdfUrl)
3. "生成简历"按钮逻辑：先调 updateResume 保存 → 再调 generateResume → 成功 alert("简历生成成功") → 失败 alert(错误信息)
4. 生成中按钮显示 loading 状态
5. 将 alert("保存成功") 改为轻提示或保留不变

**验证：** 画布有内容时点"生成简历"，后端生成 PDF 并提示成功

## T7: ResumeCard 下载更新

**文件：** `frontend/src/components/ResumeCard.tsx`
**依赖：** T5
**步骤：**
1. 修改三点菜单"下载"逻辑：不再 alert("PDF 下载功能开发中")
2. 改为直接触发 PDF 下载：`window.open(api.getDownloadUrl(resume.id))` 或创建隐藏 `<a>` 标签触发下载

**验证：** 点击下载 → 浏览器下载 PDF 文件

## 执行顺序

```
T1 → T2 → T3 → T4
                  ↘
                    T5 → T6 + T7（可并行）
```
