# 个人信息字段脱敏 Checklist

> 每一项通过运行代码或观察行为验证，聚焦系统行为。Python 解释器：`D:\coding\Anaconda\envs\agent\python.exe`。

## 实现完整性

- [ ] `getPersonalInfo` 工具注册成功，无 import / 注册错误
  （验证：`python -c "import asyncio; from src.tools.registry import ToolRegistry; r=ToolRegistry.get_instance(); r.discover('src.tools.builtin'); t=r.get_tool('getPersonalInfo'); print(t is not None); res=asyncio.run(r.execute('getPersonalInfo', {})); print(res.output[:200])"`，输出 `True` 且为 JSON/提示文本）
- [ ] 工具参数 schema 无必填属性（无参可调用）
  （验证：同上脚本输出 `r.list_definitions()` 中 `getPersonalInfo` 的 `input_schema`，`properties` 为空、`required` 为空或缺失）
- [ ] 前端类型检查通过
  （验证：`cd frontend && npx tsc -b` 无错误）

## 集成

- [ ] 保存个人信息后 `data/personal/profile.json` 顶层含 `masked_basic_fields`
  （验证：页面勾选字段保存后，`cat data/personal/profile.json` 可见该键，值为勾选字段键数组）
- [ ] 重新进入「个人信息管理」页面，勾选状态回填保持
  （验证：浏览器保存后刷新/重进页面，checkbox 仍为勾选状态）
- [ ] GET /api/personal 在未保存过时也返回含 `masked_basic_fields` 的结构
  （验证：临时移走 profile.json 后请求 GET /api/personal，响应含 `"masked_basic_fields": []`；事后恢复）

## 端到端场景

- [ ] 场景 1（脱敏生效）：在页面勾选「手机」「证件号码」→ 保存 → 重新进入页面，勾选保持 → 对话中让 agent 调用 `getPersonalInfo` → 返回 JSON 中 `basic_info.phone` 与 `basic_info.id_number` 为 `"***"`，`basic_info.name`、`education` 等为原值
  （验证：agent 回复内容 / 直接执行工具的 output，逐字段比对）
- [ ] 场景 2（存储不被替换）：场景 1 完成后，检查 `data/personal/profile.json`
  （验证：`cat` 文件中 `basic_info.phone`、`basic_info.id_number` 仍为原始真实值，未被替换）
- [ ] 场景 3（空值不脱敏）：勾选一个值为空的字段（如「有效期」id_valid_until 为空时）→ 调用工具
  （验证：返回 JSON 中该字段仍为 `""`，而非 `"***"`）
- [ ] 场景 4（未保存调用）：临时移走 profile.json 后直接执行工具
  （验证：返回友好提示文本、`is_error=False`，而非抛异常；事后恢复文件）
