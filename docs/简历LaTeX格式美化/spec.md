# 简历 LaTeX 格式美化 Spec

## 背景

简历管理模块已打通「画布 JSON（blocks + connections）→ LaTeX → PDF」链路。但当前 `generator.py` 输出的 `.tex` 排版不美观：

- 圆点是字面 `•` 字符加 `\\` 硬换行，而非真正的 `\item` 列表
- 标题行用固定宽度 `makebox`，时间右对齐效果生硬
- 导言区、页边距、段落缩进、页码等与手写的 example.tex 风格不一致

另外，简历文件（`data/CV/` 下的 `.json`/`.tex`/`.pdf`/照片）以随机 hex id 命名（如 `ab64e6f5beb2`），人眼无法辨认，希望改为 CV+时间命名。

## 目标

- 重写 LaTeX 生成器，使任意简历 JSON 生成的 `.tex` 与 example.tex 排版风格一致
- 导言区、宏命令、页眉、章节标题样式与 example.tex 相同
- 圆点识别为真正的 `\item` 列表
- 标题行保留 spans 内加粗、时间 `\hfill` 右对齐
- 描述段落以段落输出，不再 `\\` 硬换行
- 简历文件按 CV+时间命名，不再使用随机 hex id

## 功能需求

### F1: 导言区与宏命令

- F1.1：文档类改为 `\documentclass[11pt, a4paper]{ctexart}`，页面边距 1.5cm
- F1.2：引入 graphicx / enumitem / xcolor / tabularx / hyperref，`\pagestyle{empty}`、`\parindent=0pt`
- F1.3：定义 `\cvsection`、`\cvitemheader`、`\cvsubitem` 三个宏，与 example.tex 定义一致

### F2: 章节标题

- F2.1：每组正文用 `\cvsection{\textcolor[HTML]{365F91}{类别}}` 渲染
- F2.2：连续相同类别的块合并为一节（沿用现有分组逻辑）

### F3: 内容块渲染（统一布局）

- F3.1：逐 span 构建带加粗标记的行：span 文本转义后若 bold 则包 `\textbf{}`，按 `\n` 拆行，跳过空行（但保留恰好为 `•` 的行）
- F3.2：以「行首为 `•`」为列表边界，将行序列划分为：非列表区 + 若干列表项
- F3.3：非列表区第一行为标题行：`\noindent <标题保留加粗> \hfill <时间>\par`；无时间则省略 `\hfill`；时间按 `(?<=\d)\s*[–-]\s*(?=\d)` 规范化为 ` -- `
- F3.4：非列表区其余行为段落：`\noindent <段落>\par`
- F3.5：每个列表项内多行折叠为空格，合并进单个 `\begin{itemize}[leftmargin=1.5em, itemsep=0pt, parsep=0pt, topsep=0ex]` 环境
- F3.6：`bulletPoints` 字段不再参与判定（已选「自动识别 `•`」）
- F3.7：空内容块（无有效行）不输出任何内容

### F4: 个人信息头部

- F4.1：姓名居中 `{\huge\bfseries 姓名}\\[1.5ex]`
- F4.2：联系方式用动态列数 tabular，列间 `@{\quad | \quad}` 分隔，带「手机号：/ 邮箱：/ 现居地：」标签（仅存在字段才输出）
- F4.3：有照片时在右上角输出 `\vspace{-4cm}\hfill\raisebox{-\height}{\includegraphics[width=2.5cm,height=3.5cm]{本地照片路径}}`（照片路径沿用现有 `data/CV/{id}_photo.*` 解析）

### F5: 间距与组装

- F5.1：同节内块之间 `\vspace{5pt}`
- F5.2：组装顺序：导言区 → `\begin{document}` → 页眉（含照片）→ 各节 → `\end{document}`

### F6: 编译链路不变

- F6.1：复用 `compile_latex`，不改编译逻辑；输出仍为 `data/CV/{id}.tex` → `.pdf`

### F7: 简历文件按 CV+时间 命名

- F7.1：新建简历时，id 由随机 hex 改为 `CV-{YYYYMMDD-HHMMSS}`（本地时间），同一秒内冲突时追加 `-2`、`-3`… 后缀
- F7.2：`data/CV/` 下所有简历文件（`.json`、`.tex`、`.pdf`、`_photo.*`）均以该 id 为文件名，如 `CV-20260812-161430.json`
- F7.3：旧 id 简历（随机 hex）保持可正常加载、生成、预览、下载，不做批量迁移
- F7.4：前端展示的简历名称（`name` 字段）与 id 无关，保持不变

## 非功能需求

- N1：现有数据（`ab64e6f5beb2.json`）无需改动即可生成
- N2：生成器为纯函数（dict → .tex 字符串），无外部 API 依赖
- N3：LaTeX 特殊字符转义沿用现有 `_escape_latex` 逻辑
- N4：不引入新依赖

## 不做的事

- 按类别特化排版（教育/项目各自独立模板）——已确认选统一布局
- 修改前端编辑器、数据结构、`bulletPoints` 语义
- 修改 `compile_latex` / pdflatex 调用
- 照片自动定位算法（沿用 example.tex 手工负间距方式）
- 多栏布局 / 模板选择 / 简历评分
- 为旧 id 简历做批量重命名迁移（旧文件保留原名，仍可读写）

## 验收标准

- AC1：用 `ab64e6f5beb2.json` 生成 `.tex`，导言区与 example.tex 一致（ctexart、1.5cm、三个宏定义）
- AC2：教育经历块输出 `<标题保留加粗> \hfill 时间` 形式，仅学校名加粗，学位/学院/专业不加粗
- AC3：项目经历块所有 `•` 内容全部转换为 `\item`，且位于 itemize 环境内
- AC4：生成的 `.tex` 中无字面 `•` 字符、无段落间 `\\` 硬换行
- AC5：时间显示为 `2020.09 -- 2024.06` 格式
- AC6：章节标题为 `\cvsection{\textcolor[HTML]{365F91}{...}}`
- AC7：页眉为居中姓名 + tabular 联系方式，无照片时无 `\includegraphics`
- AC8：本机有 pdflatex 时，生成的 `.tex` 编译无错误，PDF 可打开（对照 example.tex 用同命令编译）
- AC9：新建简历后 `data/CV/` 出现 `CV-{时间}.json`，点击「生成简历」后同名 `.tex`/`.pdf` 生成成功
- AC10：同一秒内连续新建两份简历，文件名不冲突（第二份带 `-2` 后缀）
- AC11：旧 id 简历（如 `ab64e6f5beb2.json`）仍可正常加载、生成、预览
