# 投递流程状态机 Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性
- [ ] `submit_flow.py` 已实现并可被调用（验证：`import src.chat.submit_flow` 不报错）
- [ ] `mapping_functions.py` 已实现并可被调用（验证：`import src.chat.mapping_functions` 不报错）
- [ ] `ChatState` 包含 `submit_flow` 字段（验证：图编译通过，含 entry_router）
- [ ] `browser_navigate` 后流程由状态机接管，不是 LLM 点击全部 8 步（验证：跑完整流程，观察节点路由日志）
- [ ] `submit_flow` 进入后 `unfilled_fields` / `dropdowns` / `personal_info` 各节点写回正确（验证：单测断言 state 字段）

## 集成
- [ ] 流程任意阶段重启 app 后回话恢复（验证：模拟两次请求，会话 JSON 含 `submit_flow`，第二次继续原阶段）
- [ ] `routes.py` 正确注入/写回 `submit_flow`（验证：双请求跑完流程，会话 JSON 出现/清空 `submit_flow` 字段）
- [ ] `prompt.py` 不再引用已删除的 `_SUBMIT_FLOW_NEXT` / `_SUBMIT_FLOW_TOOLS` 用于图路由（验证：grep 无 graph 对该两变量的调用）
- [ ] 测试中用 stub client 验证 ordinary ReAct 不受影响（验证：原非投递测试通过）

## 编译与测试
- [ ] `python -m pytest tests/chat -x` 全绿（验证：运行并观察退出码）
- [ ] `python -c "import src.prompt.prompt; src.prompt.prompt.build_system_prompt()"` 不报语法/断链（验证：命令无输出/退出码 0）

## 端到端场景
- [ ] 场景 1（单简历）：用户发送投递 URL → LLM 调 `browser_navigate` → mock 浏览器后自动走 `snapshot_form → upload_resume → snapshot_again → get_personal_info → fill_form → probe_dropdowns → fill_dropdowns → completed`，最终输出「表单填写完成」（验证：mock registry 的调用序列，断言每个 call 顺序且无重复 snapshot / personal_info）
- [ ] 场景 2（多简历候选）：若 data/CV 有多份，断言停在 `waiting_resume_choice` 且 output 含候选清单；用户回复「1」再续跑至 completed（验证：mock resolve_resume 多份路径）
- [ ] 场景 3（错误中止）：工具失败返回 error → 断言流程终止、`submit_flow` 清除、回到普通对话（验证：mock 工具 is_error=True）

## 通过标准
- 以上所有条目通过，且普通对话路径无 regression。