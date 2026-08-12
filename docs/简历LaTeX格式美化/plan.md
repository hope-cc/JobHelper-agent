# 简历 LaTeX 格式美化 Plan

## 架构概览

改动集中在两个模块，其余全链路不动：

| 模块 | 改动 |
|------|------|
| `src/latex/generator.py` | **重写**渲染逻辑：导言区/宏命令/页眉对齐 example.tex；统一「标题行+段落+列表」的内容块渲染 |
| `src/api/resume_storage.py` | 简历 id 由随机 hex 改为 CV+时间，联动 `data/CV/` 下所有文件名 |
| `tests/test_latex_generator.py` | **新增**聚焦测试 |
| `compiler.py` / `resume_routes.py` / 前端 | **不改**（编译链路与路由对 id 内容透明） |

## 核心接口

| 函数 | 职责 |
|------|------|
| `generate_latex(resume_data) -> str` | 主入口，blocks+connections → 完整 .tex 字符串 |
| `_build_lines_with_bold(spans) -> list[str]` | 逐 span 转义并包 `\textbf{}`，按 `\n` 拆行；丢空行但保留恰好为 `•` 的行 |
| `_partition_block(lines) -> (head, bullets)` | 首个 `•` 行之前 = 非列表区；每个 `•` 行到下一个 `•` 行之间合并为一个列表项（内部行空格连接） |
| `_normalize_time(ts) -> str` | `re.sub(r"(?<=\d)\s*[–-]\s*(?=\d)", " -- ", ts)` 规范化日期区间 |
| `_render_content_block` / `_render_personal_info` / `_render_section` | 各区块渲染 |
| `_PREAMBLE` 常量 | 镜像 example.tex 导言区 |
| `resume_storage._generate_resume_id() -> str` | `CV-YYYYMMDD-HHMMSS`，同秒冲突追加 `-2/-3` |

## 内容块渲染规则（统一布局）

```
行序列 → 划分:
  非列表区 head = 第一个「•」行之前的所有行
  列表项    = 每个「•」行之后到下一个「•」行之间的行(合并为一项)

渲染:
  标题行 = head[0]（保留 spans 加粗）
    → 有时间: \noindent <标题> \hfill <时间>\par
    → 无时间: \noindent <标题>\par
  段落   = head[1:] → 每行 \noindent <段落>\par
  列表   = 全部列表项 → 单个 itemize[leftmargin=1.5em, itemsep=0pt, parsep=0pt, topsep=0ex]
```

**间距**：标题后若有段落则 `\vspace{0.5ex}`（模仿 `\cvitemheader` 尾部间距）；标题后直接跟列表则不补（教育经历紧贴 itemize，与 example.tex 一致）。同节块间 `\vspace{5pt}`；节间由 `\cvsection` 自带 `\vspace{2ex}`。

## 个人信息头部

```
\begin{center}
    {\huge \bfseries 姓名} \\[1.5ex]
    \begin{tabular}{动态列: 首列 @{\hspace{0pt}}l，后续 @{\quad | \quad}l}
    手机号：xxx & 邮箱：xxx & 现居地：xxx
    \end{tabular}
\end{center}
有照片时追加:
\vspace{-4cm}
\hfill
\raisebox{-\height}{\includegraphics[width=2.5cm,height=3.5cm]{本地照片路径}}
```

照片路径解析沿用现有逻辑：从 `photoUrl`（`/api/resumes/{id}/photo`）提取 id → glob `data/CV/{id}_photo.*` → 绝对路径。

## 模块交互与文件组织

```
generate_latex(data) ─→ 写 data/CV/{id}.tex ─→ compile_latex(id) ─→ data/CV/{id}.pdf
resume_storage: 时间 id 贯通 .json / .tex / .pdf / _photo.* 命名

src/latex/generator.py         — 重写渲染（核心）
src/api/resume_storage.py      — 仅改 _default_resume id 生成
tests/test_latex_generator.py  — 新增测试
docs/简历LaTeX格式美化/spec.md — 已保存
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 内容块渲染 | 统一布局 + `•` 分块 | 用户已确认；对三类数据均正确映射 |
| 标题行 | 行内 `<标题> \hfill <时间>`，**不用** `\cvitemheader` | `\cvitemheader` 会 `{\bfseries}` 整行加粗，教育经历的「学位/学院」会被误加粗；`cvitemheader/cvsubitem` 宏仍保留在导言区以镜像 example.tex |
| 文件名 | id 即文件名（时间命名） | 一处改动贯通所有文件，且旧 id 简历天然兼容 |
| 时间归一化 | 正则替换为 ` -- ` | 直接对齐 example.tex 的 `2020.09 -- 2024.06` |
| 标题内多空格 | 保留原文 | LaTeX 自动折叠为单空格，不做 `\quad` 转换（数据驱动、不猜字段） |
| 依赖/测试 | 零新依赖；pytest 验证 | 项目已有 pytest 环境 |
