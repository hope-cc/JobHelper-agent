# 基于 Playwright MCP 的简历投递表单自动填写 Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性
- [ ] `src/browser_mcp/` 四个模块存在且可导入（验证：`python -c "import src.browser_mcp.client, src.browser_mcp.fill, src.browser_mcp.upload"` 无报错）
- [ ] 四个工具已实现且可被注册中心发现（验证：`ToolRegistry.discover()` 后 `list_definitions()` 含 browser_navigate / browser_snapshot / browser_upload_resume / browser_fill_form）
- [ ] `prompt/prompt.py` 包含投递工作流描述（验证：`build_system_prompt()` 输出含「简历投递」流程）

## 脱敏
- [ ] `browser_fill_form` 返回值中，`masked_basic_fields` 对应的数据键显示 `***`（验证：单测 test_fill_tools 断言）
- [ ] 真实敏感值只出现在传给 MCP 的参数里（验证：读代码确认 resolve 真实值→call MCP 发生在同一函数、不写入返回文本）

## 功能
- [ ] `browser_navigate`：URL 为空/非法返回明确错误（验证：单测或 probe）
- [ ] `browser_snapshot`：返回控件列表含 ref/类型/标签/当前值，能标记上传候选（验证：probe 打印结构）
- [ ] `browser_upload_resume`：data/CV 无 PDF → 明确提示；多份 → 返回候选清单并询问用户；单份 → 上传并等待解析（验证：单测 resolve_resume + probe）
- [ ] `browser_fill_form`：按 ref+数据键 填写并返回已填/失败/未匹配报告（验证：probe 对 data: 表单页）
- [ ] MCP 服务未启动时调用任意工具 → 返回「无法连接 Playwright MCP 服务」错误文本而非崩溃（验证：关停服务后 probe 或手动调用）

## 编译与测试
- [ ] 后端启动无导入/注册错误，日志列出 4 个工具（验证：`python -m src.api.main`）
- [ ] `python -m pytest tests/browser_mcp -q` 全部通过

## 端到端场景
- [ ] 场景 1：MCP 服务启动（有头）+ 后端启动，本地 data: 表单页跑 snapshot→upload→fill，报告包含已填项且不含真实敏感值（验证：`scripts/probe_mcp_form.py` 各环节 PASS）
- [ ] 场景 2：真实投递流程：用户给 URL → agent browser_navigate 打开 → 用户登录回复「继续」→ agent 依次 snapshot/upload/snapshot/getPersonalInfo/fill_form（验证：前端聊天观察工具调用序列与最终报告）
