# 个人信息管理-字段自定义 Checklist

> 每一项通过运行代码或观察行为验证，聚焦系统行为。

## 实现完整性
- [ ] 页面不再展示「实习经历」「项目经历」分区（验证：打开个人信息管理页观察）
- [ ] 基本信息区默认显示 10 个预设字段，每个字段有脱敏勾选与删除操作（验证：页面渲染）
- [ ] 可新增自定义字段（标签+类型，下拉可选选项），保存后刷新仍在（验证：操作+刷新）
- [ ] 可修改字段标签，改名后已填值不丢失、脱敏状态不变、键名不变（验证：操作+保存后看 profile.json）
- [ ] 可调整字段顺序，保存后刷新顺序保持（验证：操作+刷新）
- [ ] 可删除字段（含预设字段），删除后值、脱敏标记一并清除（验证：操作+保存后看 profile.json）
- [ ] 自定义字段可勾选脱敏，agent 读取时显示 `***`，profile.json 原始值不变（验证：调用 getPersonalInfo）

## 集成
- [ ] 保存后 profile.json 含 `basic_fields_schema`，且不含 `internship`/`project`（验证：查看 data/personal/profile.json）
- [ ] `getPersonalInfo` 返回含 `basic_fields_schema`（键↔标签映射），且不含实习/项目（验证：调用工具看返回）
- [ ] 前端 `PersonalProfile`/`SavableProfile` 与后端 `PersonalProfileBody`/`empty_profile` 结构一致（验证：编译 + 保存往返）
- [ ] LLM 取值/脱敏路径仍工作：`browser_mcp` 既有测试通过（验证：pytest）

## 编译与测试
- [ ] 后端现有测试全部通过（验证：`python -m pytest`）
- [ ] 前端构建通过（验证：`cd frontend && npm run build`）
- [ ] 前端 lint 通过（验证：`cd frontend && npm run lint`）

## 端到端场景
- [ ] 场景 1（中文自定义字段+脱敏）：新增标签「微信号」并勾选脱敏 → 填值 → 保存 → 刷新字段仍在 → `getPersonalInfo` 返回 `basic_info.微信号` 且值为 `***`，profile.json 中为原值
- [ ] 场景 2（删除字段后 LLM 跳过）：删除「手机」字段 → 保存 → profile.json 无 `phone` 键 → `resolve_profile_value(p, "basic_info.phone")` 返回 `None`（表单填写自动跳过）
- [ ] 场景 3（改名不改键）：把「姓名」标签改为「真实姓名」→ 保存 → profile.json 中 `basic_info.name` 键不变、值保留、脱敏列表不含新键
