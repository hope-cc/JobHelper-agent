# 简历 LaTeX 格式美化 Checklist

> 每一项通过运行代码或观察行为来验证。

## 实现完整性

- [ ] 导言区与 example.tex 一致：`\documentclass[11pt, a4paper]{ctexart}`、1.5cm 边距、`\pagestyle{empty}`、`\parindent=0pt`（验证：生成 .tex 后 grep）
- [ ] 三个宏 `\cvsection` / `\cvitemheader` / `\cvsubitem` 定义存在（验证：grep 生成输出）
- [ ] 章节标题为 `\cvsection{\textcolor[HTML]{365F91}{类别}}`，连续同类别合并为一节（验证：生成输出 grep + 对比 data 类别数）
- [ ] 教育经历块：仅学校名 `\textbf{}`，学位/学院/专业不加粗，时间 `\hfill` 右对齐（验证：grep 教育块输出行）
- [ ] 项目/实习块：所有 `•` 内容转为 `\item`，位于 itemize 内，描述段落为 `\noindent ...\par`（验证：grep 项目块输出）
- [ ] 专业技能块：无标题行、纯 itemize（验证：grep 技能块输出）
- [ ] 时间显示为 `2020.09 -- 2024.06` 格式（验证：grep）
- [ ] 生成的 .tex 无字面 `•` 字符、无段落间 `\\`（验证：grep -c）
- [ ] 页眉：居中姓名 + 动态 tabular（手机号：/ 邮箱：/ 现居地：），无照片时不出现 `\includegraphics`（验证：grep 输出）
- [ ] 空内容块不输出任何 LaTeX（验证：构造空 spans 块）

## 集成

- [ ] 新建简历 id 为 `CV-YYYYMMDD-HHMMSS`，`data/CV/` 下 `.json` 以该 id 命名（验证：调用 create 或直接调 `_default_resume`）
- [ ] 同秒连续新建两份简历，第二份文件名带 `-2` 后缀（验证：单测覆盖）
- [ ] 旧 id 简历（`ab64e6f5beb2.json`）仍可 load / generate / preview（验证：调 `load_resume("ab64e6f5beb2")` + 生成 .tex 成功）
- [ ] 编译链路复用 `compile_latex` 未改动（验证：git diff compiler.py 为空）
- [ ] 路由 / photoUrl / 前端未改动（验证：git diff resume_routes.py / frontend 为空）

## 编译与测试

- [ ] `python -m pytest tests/test_latex_generator.py -q` 全绿（验证：运行命令看输出）
- [ ] `python -c "import src.latex.generator"` 无导入错误（验证：运行命令）

## 端到端场景

- [ ] 场景 1（真实数据生成）：用 `data/CV/ab64e6f5beb2.json` 调 `generate_latex` 生成 .tex → 本机 pdflatex 编译 → 无 `!` 错误 → PDF 存在且可打开（验证：跑命令 + 打开 PDF）
- [ ] 场景 2（新建→生成）：新建简历得到 `CV-{时间}.json` → 填入块数据保存 → 触发 generate → `CV-{时间}.tex` 与 `.pdf` 生成成功（验证：走 API 或直接函数调用，检查文件存在）
