# 简历 LaTeX 格式美化 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `src/latex/generator.py` | 重写渲染：导言区常量、分块算法、区块渲染、组装 |
| 修改 | `src/api/resume_storage.py` | id 时间化生成 |
| 新建 | `tests/test_latex_generator.py` | 生成器单元测试 |
| 新建 | `docs/简历LaTeX格式美化/checklist.md` | 验收设计（下一阶段） |

## T1: 生成器基础常量与行分块算法

**文件：** `src/latex/generator.py`
**依赖：** 无
**步骤：**
1. 删除 `_render_preamble()` 函数，新增模块级常量 `_PREAMBLE`（镜像 example.tex 导言区：ctexart、geometry 1.5cm、graphicx/enumitem/xcolor/tabularx/hyperref、`\pagestyle{empty}`、`\parindent{0pt}`、`\cvsection`/`\cvitemheader`/`\cvsubitem` 三个宏）和 `_ITEMIZE_OPTS = "leftmargin=1.5em, itemsep=0pt, parsep=0pt, topsep=0ex"`
2. 新增 `_normalize_time(ts)`：`re.sub(r"(?<=\d)\s*[–-]\s*(?=\d)", " -- ", ts)`
3. 新增 `_build_lines_with_bold(spans)`：逐 span 转义（`_escape_latex`），bold 则包 `\textbf{}`，按 `\n` 拆行；strip 后丢空行，但保留 strip 后恰好为 `"•"` 的行
4. 新增 `_partition_block(lines)`：返回 `(head, bullets)`；首个 `•` 行之前 → head；`•` 行之后到下一个 `•` 行之间的行合并（`" ".join`）为一个列表项；`•` 行去掉 `•` 前缀后作为该项首行

**验证：** 用 python 交互调用 `_build_lines_with_bold` + `_partition_block` 处理项目块 spans，断言 head 首行为标题、bullets 长度正确、内部 `\n` 折叠为空格

## T2: 区块渲染函数

**文件：** `src/latex/generator.py`
**依赖：** T1
**步骤：**
1. 新增 `_resolve_photo_path(photo_url)`：从 `/api/resumes/{id}/photo` 提取 id → glob `DATA_DIR/{id}_photo.*` → 绝对路径（`/` 分隔）；无匹配返回空串
2. 重写 `_render_personal_info(block)`：居中姓名 `{\huge\bfseries 姓名}\\[1.5ex]`；动态列 tabular（首列 `@{\hspace{0pt}}l`，后续 ` @{\quad | \quad}l`），字段带「手机号：/ 邮箱：/ 现居地：」标签；有照片追加 `\vspace{-4cm}\n\hfill\n\raisebox{-\height}{\includegraphics[width=2.5cm,height=3.5cm]{path}}`
3. 重写 `_render_content_block(block)`：空 spans / 无有效行返回空串；调 `_build_lines_with_bold` + `_partition_block`；按 plan 间距规则输出标题行/段落/列表
4. 重写 `_render_section(group)`：`\cvsection{\textcolor[HTML]{365F91}{类别}}`；块间 `\vspace{5pt}`；空块跳过

**验证：** 运行既有生成逻辑，`_render_content_block` 对教育块输出含 `\hfill` 且学校名 `\textbf{}`；对项目块输出 itemize 且无字面 `•`；对技能块输出纯 itemize

## T3: generate_latex 组装

**文件：** `src/latex/generator.py`
**依赖：** T2
**步骤：**
1. 重写 `generate_latex`：`_PREAMBLE` + `\begin{document}` + 个人信息 + 各节 + `\end{document}`，块间 `\n\n` 连接
2. 保留 `_sort_blocks` / `_group_sections` / `_escape_latex` / `_get_field` 等既有辅助函数不变

**验证：** 用 `data/CV/ab64e6f5beb2.json` 调 `generate_latex`，输出含 `ctexart`、`\cvsection{\textcolor[HTML]{365F91}{...}}`、`\item`、` -- `，且不含字面 `•` 与段落间 `\\`

## T4: 简历 id 时间化

**文件：** `src/api/resume_storage.py`
**依赖：** 无
**步骤：**
1. 新增 `_generate_resume_id()`：`"CV-" + datetime.now().strftime("%Y%m%d-%H%M%S")`；若 `DATA_DIR/{candidate}.json` 已存在，追加 `-2`、`-3`… 后缀
2. 修改 `_default_resume`：`"id"` 由 `uuid.uuid4().hex[:12]` 改为 `_generate_resume_id()`
3. 若无其他用途，移除 `import uuid`

**验证：** 交互调用 `_generate_resume_id()` 两次，格式为 `CV-YYYYMMDD-HHMMSS`；临时占用同名文件后确认返回 `-2` 后缀

## T5: 新增单元测试

**文件：** `tests/test_latex_generator.py`
**依赖：** T1-T4
**步骤：**
1. 测试 `_normalize_time`：`2020.09-2024.06`、`2025.06 - 2026.04`、`2024.09 – 2027.06` 均 → ` -- ` 格式；已含 `--` 的不重复转换
2. 测试 `generate_latex` 用内联最小 fixture（教育/项目/技能三种块）：断言无 `•`、有 `\item`、标题含 `\hfill`、教育块仅学校名 `\textbf{}`
3. 测试 `resume_storage._generate_resume_id` 格式与冲突后缀

**验证：** `python -m pytest tests/test_latex_generator.py -q` 全绿

## T6: 端到端验证

**文件：** 无
**依赖：** T3-T5
**步骤：**
1. 用真实数据 `data/CV/ab64e6f5beb2.json` 生成 .tex 到临时文件，目检格式
2. 本机有 pdflatex 时编译生成 .tex 对照 example.tex 同命令编译，确认无错误

**验证：** 生成的 .tex 内容与 example.tex 风格一致；编译无 `!` 错误行

## 执行顺序

```
T1 → T2 → T3 → T4 → T5 → T6
```
