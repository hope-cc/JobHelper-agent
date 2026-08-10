# LaTeX 生成与 PDF 导出 Plan

## 架构概览

整体分两层：

**后端层（Python）：** 新增 `src/latex/` 包，包含生成器和编译器两个模块。`generator.py` 负责 blocks+connections → LaTeX 字符串；`compiler.py` 负责调用 pdflatex 编译。更新 `resume_routes.py` 的 `/generate` 端点实现真正逻辑，新增 `/preview` 和 `/download` 端点。

**前端层（React）：** 更新 `EditorToolbar`，"生成简历"左边增加"预览"按钮，替换 alert 为真实 API 调用。更新 `ResumeCard` 三点菜单中的"下载"按钮对接 `/download`。新增 `resumeClient.ts` 中的 `generateResume` 函数。

## 核心数据结构

### LaTeX 生成输入

输入即现有的 Resume JSON（blocks + connections），无需新增类型。

### 生成器内部中间结构

```python
@dataclass
class SortedBlock:
    """按连线顺序排列后的块，附带排序索引"""
    block: dict
    order: int

@dataclass  
class SectionGroup:
    """同一模块类型的连续块归为一组"""
    category: str          # 模块类型
    blocks: list[dict]     # 该组内的块
```

## 模块设计

### 模块 A: LaTeX 代码生成器（`src/latex/generator.py`）

**职责：** 将 Resume 数据转换为完整 LaTeX 源码字符串
**对外接口：**
- `generate_latex(resume_data: dict) -> str` — 主入口，返回完整 .tex 源码

**内部流程：**
1. `_sort_blocks(blocks, connections)` — 从个人信息块出发沿连线链遍历，返回排序列表
2. `_group_sections(sorted_blocks)` — 将连续同类正文块分组
3. `_render_preamble()` — LaTeX 导言区（documentclass、宏包、颜色、section 格式、\cvitemheader 定义）
4. `_render_personal_info(block)` — 个人信息区（minipage 左右布局）
5. `_render_section(group)` — 单个 section 组（标题 + 横线 + 正文）
6. `_render_content_block(block)` — 单个正文块（\cvitemheader + 加粗 + 列表）
7. `_spans_to_latex(spans, bullet_points)` — TextSpan 转 LaTeX 行内命令

**依赖：** 无外部库

### 模块 B: LaTeX 编译器（`src/latex/compiler.py`）

**职责：** 调用 pdflatex 编译 .tex → .pdf
**对外接口：**
- `compile_latex(resume_id: str) -> CompileResult` — 编译指定简历，返回结果

**内部流程：**
1. 在 `data/CV/` 目录下执行 `pdflatex -interaction=nonstopmode {id}.tex`
2. 设置 30 秒超时
3. 收集 stdout/stderr
4. 检查 PDF 是否生成
5. 清理辅助文件（.aux, .log）
6. 返回 CompileResult（success + pdf_path 或 error_message）

**依赖：** subprocess、os

### 模块 C: API 路由更新（`src/api/resume_routes.py`）

**职责：** 替换 501 占位，实现真正的 generate/preview/download
**变更：**
- `POST /resumes/{id}/generate` — 更新简历数据 → 调用 generator → 调用 compiler → 返回结果
- `GET /resumes/{id}/preview` — 返回 PDF 文件（inline 显示）
- `GET /resumes/{id}/download` — 返回 PDF 文件（attachment 下载）

### 模块 D: 前端 EditorToolbar 更新

**变更：**
- "生成简历"按钮左边新增"预览"按钮
- "生成简历" → 先保存再调用 generate API
- "预览" → 调用 compile → window.open preview URL
- 处理编译成功/失败提示

### 模块 E: 前端 ResumeCard "下载"更新

**变更：**
- 三点菜单"下载"不再 alert，改为真正下载 PDF

### 模块 F: 前端 API Client 更新（`resumeClient.ts`）

**新增函数：**
- `generateResume(id)` → POST `/api/resumes/{id}/generate`
- `getPdfUrl(id)` → 返回 `/api/resumes/{id}/preview` URL 字符串
- `getDownloadUrl(id)` → 返回 `/api/resumes/{id}/download` URL 字符串

## 模块交互

```
用户点击"生成简历"
  → EditorToolbar.handleGenerate()
    → resumeClient.updateResume() 保存当前状态
    → resumeClient.generateResume()  → POST /api/resumes/{id}/generate
      → resume_routes.generate_resume()
        → resume_storage.save_resume() 保存最新数据
        → latex_generator.generate_latex(data) → .tex 字符串
        → 写入 data/CV/{id}.tex
        → latex_compiler.compile_latex(id) → pdflatex → .pdf
        → 返回 {success, pdf_url} 或 {success:false, error}
    → 前端显示成功/失败提示

用户点击"预览"
  → window.open("/api/resumes/{id}/preview") → 浏览器打开 PDF

用户点击"下载"
  → <a href="/api/resumes/{id}/download" download> → 浏览器下载 PDF
```

## 文件组织

```
src/latex/
├── __init__.py           # 新建：导出 generate_latex, compile_latex
├── generator.py          # 新建：LaTeX 代码生成
└── compiler.py           # 新建：pdflatex 编译

src/api/
└── resume_routes.py      # 修改：generate/preview/download 端点

frontend/src/
├── api/resumeClient.ts   # 修改：新增 generateResume, getPdfUrl, getDownloadUrl
├── components/
│   ├── EditorToolbar.tsx # 修改：新增预览按钮，generate 调真实 API
│   └── ResumeCard.tsx    # 修改：下载按钮调真实 API
```

## LaTeX 模板设计

### 导言区
```latex
\documentclass[11pt,a4paper]{article}
\usepackage[UTF8]{ctex}
\usepackage[margin=2cm]{geometry}
\usepackage{xcolor}
\usepackage{graphicx}
\usepackage{titlesec}
\usepackage{enumitem}

\definecolor{sectioncolor}{HTML}{365F91}

\titleformat{\section}
  {\Large\bfseries\color{sectioncolor}}
  {}{0em}{}[\titlerule]

\newcommand{\cvitemheader}[2]{%
  \makebox[0.7\textwidth][l]{\textbf{#1}}%
  \makebox[0.3\textwidth][r]{\small\textit{#2}}%
}
```

### 个人信息
```latex
\begin{minipage}{0.7\textwidth}
  {\centering\Huge\bfseries 张三\par}
  \vspace{0.3cm}
  {\centering 13800000000 $|$ zhangsan@example.com $|$ 北京\par}
\end{minipage}%
\begin{minipage}{0.3\textwidth}
  \flushright
  \includegraphics[width=3cm,height=3.5cm,keepaspectratio]{photo.jpg}
\end{minipage}
```

### 正文
```latex
\section{项目经历}
\cvitemheader{项目名称或第一行}{2020.09 - 2024.06}

第二行内容

\begin{itemize}
  \item 第一点
  \item 第二点
\end{itemize}
\vspace{5pt}

下一个同类块的正文...
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| LaTeX class | article + ctex | 简单、中文支持好、无额外模板依赖 |
| 照片布局 | minipage 左右分栏 | 灵活控制比例，不依赖 wrapfig |
| 标题格式 | titlesec 宏包 | \titlerule 直接实现标题下方横线 |
| section 颜色 | 重定义 \section 格式 | 一次设置全局生效 |
| \cvitemheader | 自定命令，\makebox 分栏 | 左文字右时间的标准简历格式 |
| 编译引擎 | pdflatex | 用户指定，兼容性最广 |
| 编译位置 | data/CV/ 目录 | 与 JSON/照片同目录，相对路径简单 |
| 预览方式 | 新标签页打开 | 无需额外 UI，浏览器原生 PDF 查看 |
