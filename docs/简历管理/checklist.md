# LaTeX 生成与 PDF 导出 Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性
- [ ] [generator.py] generate_latex 可被导入调用（验证：`from src.latex import generate_latex` 无错误）
- [ ] [compiler.py] compile_latex 可被导入调用（验证：`from src.latex import compile_latex` 无错误）
- [ ] [resume_routes] /generate 返回真实 PDF URL 而非 501（验证：POST generate 返回 200 + pdf_url）
- [ ] [resume_routes] /preview 返回 PDF 文件（验证：浏览器打开 /preview 显示 PDF）
- [ ] [resume_routes] /download 触发文件下载（验证：浏览器打开 /download 触发下载）
- [ ] [resumeClient] 三个新函数编译通过（验证：`npx tsc --noEmit`）
- [ ] [EditorToolbar] 预览按钮出现并可用（验证：页面可见预览+生成两个按钮）
- [ ] [ResumeCard] 下载菜单项触发下载（验证：点击下载 → 浏览器下载 PDF）

## LaTeX 格式验证
- [ ] 个人信息：姓名居中加粗（验证：PDF 中查看）
- [ ] 个人信息：联系方式居中、照片右侧（验证：PDF 中查看）
- [ ] 正文：标题颜色为 #365F91（验证：PDF 中查看，蓝色调）
- [ ] 正文：标题下方有横线分隔（验证：PDF 中查看）
- [ ] 正文：时间跨度在正文第一行末尾（验证：PDF 中查看）
- [ ] 正文：加粗文字确实加粗显示（验证：PDF 中查看）
- [ ] 正文：圆点列表渲染为 bullet item（验证：PDF 中查看）
- [ ] 同类型正文块合并不重复标题（验证：连续两个"项目经历"块 → 只有一个标题）
- [ ] 同类型块之间用 5pt 间距分隔（验证：PDF 中块之间有视觉间隔）

## 编译与测试
- [ ] 后端启动无报错（验证：`uvicorn src.main:app` 正常启动）
- [ ] 前端编译无错误（验证：`npm run build` 通过）
- [ ] 前端 lint 无错误（验证：`npm run lint` 通过）

## 端到端场景
- [ ] 场景 1：选中简历 → 新增个人信息块（填姓名/手机号/邮箱/现居地/照片） → 新增正文块（项目经历，加粗+圆点列表） → 连线 → 点"生成简历" → 生成成功提示 → 点"预览" → 新标签页显示正确格式的 PDF
- [ ] 场景 2：多个同类型正文块 → 生成 → PDF 只显示一个标题，内容合并
- [ ] 场景 3：点击"下载" → 浏览器下载 PDF 文件，文件名包含简历名称
- [ ] 场景 4：空画布点"生成简历" → 后端返回错误或生成基础 PDF（只有个人信息或无内容）
