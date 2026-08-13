# 投递表单下拉框选项探测与填写 Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性

- [ ] 识别模块已实现：`find_dropdown_candidates` 对真实快照识别出全部下拉框（验证：对 ouiput.txt 运行，识别出 24 个候选、排除 13 个非下拉框）
- [ ] `browser_probe_dropdowns` 无参调用即返回候选清单及未填者选项（验证：单测 + 冒烟）
- [ ] `browser_fill_dropdowns` 对 {ref, 目标值} 完成填写（验证：单测断言点击选项 ref）

## 集成

- [ ] 两个新工具被 @tool 注册并可通过 registry 发现（验证：列出工具名包含 browser_probe_dropdowns / browser_fill_dropdowns）
- [ ] SubmitFlow 描述包含 probe/fill 步骤（验证：读取 prompt.py）

## 编译与测试

- [ ] 全量 `pytest tests` 通过（含既有测试）
- [ ] 无新增依赖、无 import 错误

## 端到端场景

- [ ] 场景1（真实页面）：投递页 → `browser_probe_dropdowns` 识别未填下拉框并返回选项 → `browser_fill_dropdowns` 填「面试站点」→ 快照确认已选中（验证：连真实 MCP 冒烟脚本）
- [ ] 场景2（边界）：传入无效 ref / 目标值不匹配 / 已填下拉框 → 逐项报告、不中断、不误点（验证：单测）
