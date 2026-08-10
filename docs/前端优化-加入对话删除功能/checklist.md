# 个人信息管理导航项 + 批量删除会话 Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性

- [ ] 后端 `storage.delete_conversation()` 函数已实现（验证：`python -c "from src.api.storage import delete_conversation"` 无 ImportError）
- [ ] 后端 `DELETE /api/conversations/{conversation_id}` 路由已注册（验证：启动后端，`curl -X DELETE http://localhost:8000/api/conversations/test123` 返回 204）
- [ ] 前端 `types.ts` ViewType 包含 `"profile"`，AppState 包含 `batchDeleteMode` 和 `selectedConvIds`（验证：`npx tsc --noEmit` 编译通过）
- [ ] 前端 `AppContext.tsx` reducer 处理三个新 action（验证：`npx tsc --noEmit` 编译通过）
- [ ] 前端 `client.ts` 包含 `deleteConversation()`（验证：`npx tsc --noEmit` 编译通过）
- [ ] 前端 `NavSection.tsx` 包含第四项"个人信息管理"（验证：`npx tsc --noEmit` 编译通过）
- [ ] 前端 `MainArea.tsx` 包含 `case "profile"` 路由分支（验证：`npx tsc --noEmit` 编译通过）
- [ ] 前端 `ConversationItem.tsx` 支持 `showCheckbox` prop（验证：`npx tsc --noEmit` 编译通过）
- [ ] 前端 `ConversationList.tsx` 包含批量删除开关和删除按钮（验证：`npx tsc --noEmit` 编译通过）
- [ ] 前端 `Sidebar.tsx` 透传批量删除 props（验证：`npx tsc --noEmit` 编译通过）
- [ ] 前端 `App.tsx` 实现 handleBatchDelete（验证：`npx tsc --noEmit` 编译通过）

## 功能验收（对应 spec AC）

- [ ] **AC1**：左侧导航区出现第四项"个人信息管理"（👤图标），点击后右侧显示"个人信息管理 —— 该功能将在后续版本开发"占位页
- [ ] **AC2**：聊天记录标题旁存在"批量删除"开关，默认关闭状态，此时无勾选框和删除按钮
- [ ] **AC3**：打开批量删除开关后，每个会话项左侧出现可点击的勾选框（checkbox），开关下方出现红色"删除"按钮
- [ ] **AC4**：未勾选任何会话时"删除"按钮处于禁用（灰色）状态
- [ ] **AC5**：勾选一个或多个会话后点击"删除"，对应会话从列表中消失（验证：同时检查后端 data/conversations/ 目录下对应 JSON 文件已被删除）
- [ ] **AC6**：被删除的会话正好是当前打开的会话时，右侧视图自动回到"新聊天"页面
- [ ] **AC7**：删除完成后勾选状态清空，批量删除模式保持开启（开关仍为开、勾选框仍可见、所有勾选已清除）
- [ ] **AC8**：关闭批量删除开关后，勾选框和删除按钮全部隐藏，界面恢复常规状态

## 集成

- [ ] 前端批量删除调用后端接口，数据一致（验证：删除后刷新页面，被删会话不在聊天记录中）
- [ ] 点击勾选框不会触发会话导航（验证：在批量删除模式下勾选会话，不会跳转到该会话的聊天视图）
- [ ] 后端删除不存在的会话 ID 不报错（验证：`curl -X DELETE http://localhost:8000/api/conversations/nonexistent`，返回 204）

## 端到端场景

- [ ] **场景 1（新增导航项）**：启动应用 → 左侧导航区看到"个人信息管理" → 点击 → 右侧显示占位页 → 点击"新聊天" → 正常切回聊天 → 再次点击"个人信息管理" → 正常切换
- [ ] **场景 2（批量删除完整流程）**：有多个历史会话 → 打开批量删除开关 → 勾选其中 2 个会话 → 其中一个正好是当前正在查看的 → 点击删除 → 两个会话从列表消失 → 右侧自动切到新聊天页面 → 勾选清空、开关仍开 → 关闭开关 → 界面恢复正常
- [ ] **场景 3（取消批量删除）**：打开批量删除开关 → 勾选若干会话 → 关闭开关 → 勾选框和删除按钮隐藏 → 重新打开开关 → 勾选状态已清空，所有勾选框未选中

## 编译与测试

- [ ] `cd frontend && npx tsc --noEmit` 编译通过，零类型错误
- [ ] 后端启动无错误（`python -m src.api.main` 可以启动）
- [ ] `cd frontend && npm run build` 生产构建成功
