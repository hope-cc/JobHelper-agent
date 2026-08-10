# 个人信息管理导航项 + 批量删除会话 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `src/api/storage.py` | 新增 delete_conversation() 函数 |
| 修改 | `src/api/routes.py` | 新增 DELETE 路由 |
| 修改 | `frontend/src/types.ts` | ViewType 添加 "profile"；AppState 添加 batchDeleteMode、selectedConvIds；AppAction 添加三个新 action |
| 修改 | `frontend/src/AppContext.tsx` | initialState 和 reducer 扩展 |
| 修改 | `frontend/src/api/client.ts` | 新增 deleteConversation() |
| 修改 | `frontend/src/components/NavSection.tsx` | NAV_ITEMS 新增"个人信息管理" |
| 修改 | `frontend/src/components/MainArea.tsx` | 新增 case "profile" |
| 修改 | `frontend/src/components/ConversationItem.tsx` | 新增 showCheckbox、isSelected、onToggleSelect props，条件渲染勾选框 |
| 修改 | `frontend/src/components/ConversationList.tsx` | 新增批量删除开关、删除按钮、向 ConversationItem 透传勾选状态 |
| 修改 | `frontend/src/components/Sidebar.tsx` | 解构新 state 字段，定义回调，透传 props |
| 修改 | `frontend/src/App.tsx` | 实现 handleBatchDelete 回调 |

## 任务列表

---

### T1: storage.py — 新增 delete_conversation()

**文件：** `src/api/storage.py`
**依赖：** 无

**步骤：**
1. 在 `update_title()` 函数之后（第 80 行后）新增函数 `delete_conversation(conversation_id: str) -> bool`
2. 函数体：获取文件路径 `fp = _file_path(conversation_id)`
3. 使用 try/except `FileNotFoundError`：
   - `fp.unlink()` 删除文件
   - 返回 `True`
   - 捕获 `FileNotFoundError` 返回 `False`

**验证：** 在后端项目目录手动运行 `python -c "from src.api.storage import delete_conversation; print(delete_conversation('nonexistent'))"` 应输出 `False`，且不抛出异常

---

### T2: routes.py — 新增 DELETE 路由

**文件：** `src/api/routes.py`
**依赖：** T1（需要 delete_conversation 函数存在）

**步骤：**
1. 在 `send_message()` 路由之后（约第 187 行后）新增路由 handler
2. 路由定义：`@router.delete("/conversations/{conversation_id}")`
3. 函数签名：`async def delete_conversation(conversation_id: str)`
4. 调用 `storage.delete_conversation(conversation_id)`
5. 返回 `Response(status_code=204)`（需从 `fastapi.responses` 导入 `Response`）

**验证：** `python -c "from src.api.routes import router; print([r.path for r in router.routes if 'DELETE' in r.methods])"` 应输出包含 `/api/conversations/{conversation_id}` 的列表

---

### T3: types.ts — 扩展类型定义

**文件：** `frontend/src/types.ts`
**依赖：** 无

**步骤：**
1. `ViewType` 联合类型（第 33 行）：添加 `| "profile"`，变为 `"new_chat" | "resume" | "progress" | "conversation" | "profile"`
2. `AppState` 接口（第 36-42 行）：在 `isStreaming` 后添加两个字段：
   ```typescript
   batchDeleteMode: boolean;
   selectedConvIds: Set<string>;
   ```
3. `AppAction` 联合类型（第 45-56 行末尾 `;` 前）：添加三个新 action：
   ```typescript
   | { type: "TOGGLE_BATCH_DELETE" }
   | { type: "TOGGLE_SELECT_CONVERSATION"; conversationId: string }
   | { type: "DELETE_CONVERSATIONS"; conversationIds: string[] }
   ```

**验证：** `cd frontend && npx tsc --noEmit` 不应因 types.ts 产生编译错误（其他文件的类型错误是预期内的，尚未修改）

---

### T4: AppContext.tsx — 扩展状态管理

**文件：** `frontend/src/AppContext.tsx`
**依赖：** T3（需要类型定义）

**步骤：**
1. 在 `initialState`（第 10-16 行）中添加两个新字段的初始值：
   ```typescript
   batchDeleteMode: false,
   selectedConvIds: new Set<string>(),
   ```
2. 在 reducer 的 `switch` 中，`default` 之前（约第 128 行）添加三个新 case：
   - `case "TOGGLE_BATCH_DELETE"`：返回新 state，`batchDeleteMode` 取反；若取反后为 `false`，`selectedConvIds` 重置为 `new Set<string>()`
   - `case "TOGGLE_SELECT_CONVERSATION"`：基于当前 `selectedConvIds` 创建新 Set，若已有该 id 则 delete，否则 add；返回 `{ ...state, selectedConvIds: newSet }`
   - `case "DELETE_CONVERSATIONS"`：从 `conversations` 数组中 filter 掉 `action.conversationIds` 中包含的 id；清空 `selectedConvIds`；若 `currentConversationId` 在被删列表中，将 `currentConversationId` 和 `messages` 清空

**验证：** `cd frontend && npx tsc --noEmit` 对 AppContext.tsx 本身不应报错

---

### T5: client.ts — 新增 deleteConversation()

**文件：** `frontend/src/api/client.ts`
**依赖：** 无

**步骤：**
1. 在 `sendMessage()` 函数之后（约第 39 行后）新增函数 `deleteConversation(id: string): Promise<void>`
2. 函数体：使用 fetch 发送 DELETE 请求到 `${BASE}/conversations/${id}`
3. 若 `!res.ok` 且 status 不是 204，抛出 Error
4. 返回 `undefined`（void）

**验证：** `cd frontend && npx tsc --noEmit` 对 client.ts 不应报错

---

### T6: NavSection.tsx — 新增导航项

**文件：** `frontend/src/components/NavSection.tsx`
**依赖：** T3（需要 `"profile"` 是 ViewType 的有效值）

**步骤：**
1. 在 `NAV_ITEMS` 数组（第 9-13 行）末尾添加：
   ```typescript
   { key: "profile", label: "个人信息管理", icon: "👤" },
   ```

**验证：** `cd frontend && npx tsc --noEmit` 对 NavSection.tsx 不应报错

---

### T7: MainArea.tsx — 新增视图路由

**文件：** `frontend/src/components/MainArea.tsx`
**依赖：** T3（需要 `"profile"` 是 ViewType 的有效值）

**步骤：**
1. 在 switch 的 `case "progress"` 分支之后、`default` 之前（约第 33 行）添加：
   ```typescript
   case "profile":
     return (
       <main className="flex-1 h-full">
         <PlaceholderPage title="个人信息管理" />
       </main>
     );
   ```

**验证：** `cd frontend && npx tsc --noEmit` 对 MainArea.tsx 不应报错

---

### T8: ConversationItem.tsx — 新增勾选框

**文件：** `frontend/src/components/ConversationItem.tsx`
**依赖：** 无

**步骤：**
1. 在 `ConversationItemProps` 接口（第 3-7 行）中添加三个新字段：
   ```typescript
   showCheckbox: boolean;
   isSelected: boolean;
   onToggleSelect: () => void;
   ```
2. 在组件函数参数解构中（第 9-13 行）添加这三个新 props
3. 在 return 的 `<button>` 内部（第 24 行之前）添加条件渲染：
   - 当 `showCheckbox` 为 true 时，在标题文本前渲染一个 `<input type="checkbox">`
   - checkbox 的 `checked` 绑定 `isSelected`
   - checkbox 的 `onChange` 调用 `onToggleSelect`
   - checkbox 的 `onClick` 调用 `e.stopPropagation()` 阻止冒泡到父级 button
   - checkbox 添加 className `"mr-2"` 与标题文本保持间距
4. 标题文本用 `<span>` 包裹，与 checkbox 同行显示

**验证：** `cd frontend && npx tsc --noEmit` 对 ConversationItem.tsx 不应报错

---

### T9: ConversationList.tsx — 批量删除控制区

**文件：** `frontend/src/components/ConversationList.tsx`
**依赖：** T8（ConversationItem 新增了 props）

**步骤：**
1. 在 `ConversationListProps` 接口（第 4-8 行）中添加四个新字段：
   ```typescript
   batchDeleteMode: boolean;
   selectedIds: Set<string>;
   onToggleSelect: (id: string) => void;
   onDelete: () => void;
   onToggleBatchDelete: () => void;
   ```
2. 在组件函数参数解构中添加这五个新 props
3. 在组件 return 中，将原来单一的 `<div>` 改为包裹结构：
   - **标题行**：保留"聊天记录"文字，右侧添加一个 Toggle 开关（用 `<button>` 实现，带 `onClick={onToggleBatchDelete}`，显示"批量删除"文字+开关状态指示）
   - **删除按钮**：当 `batchDeleteMode` 为 true 时，在标题行下方渲染一个红色"删除"按钮，`disabled={selectedIds.size === 0}`，`onClick={onDelete}`
   - **会话列表区**：保持不变，但向每个 `<ConversationItem>` 传入新 props：
     ```typescript
     showCheckbox={batchDeleteMode}
     isSelected={selectedIds.has(conv.id)}
     onToggleSelect={() => onToggleSelect(conv.id)}
     ```

**验证：** `cd frontend && npx tsc --noEmit` 对 ConversationList.tsx 不应报错

---

### T10: Sidebar.tsx — props 透传

**文件：** `frontend/src/components/Sidebar.tsx`
**依赖：** T4、T9（需要 context 中有新 state，ConversationList 接受了新 props）

**步骤：**
1. 在 Sidebar 组件中新增对 `useAppState()` 和 `useAppDispatch()` 的调用（从 AppContext 导入），解构 `batchDeleteMode` 和 `selectedConvIds`
2. 定义三个回调函数：
   - `handleToggleBatchDelete = () => dispatch({ type: "TOGGLE_BATCH_DELETE" })`
   - `handleToggleSelect = (id: string) => dispatch({ type: "TOGGLE_SELECT_CONVERSATION", conversationId: id })`
   - `handleBatchDelete = () => { /* 由 App.tsx 通过 props 传入 */ }` —— 实际上从 App.tsx 以 prop 传入
3. 在 `SidebarProps` 接口（第 5-11 行）中新增 `onBatchDelete: () => void`
4. 从 props 解构 `onBatchDelete`
5. 将 `batchDeleteMode`、`selectedIds={selectedConvIds}`、`onToggleSelect={handleToggleSelect}`、`onDelete={onBatchDelete}`、`onToggleBatchDelete={handleToggleBatchDelete}` 传给 `<ConversationList>`

**验证：** `cd frontend && npx tsc --noEmit` 对 Sidebar.tsx 不应报错

---

### T11: App.tsx — 删除逻辑编排

**文件：** `frontend/src/App.tsx`
**依赖：** T4、T5、T10（需要 context、api、Sidebar 准备就绪）

**步骤：**
1. 在 `AppShell` 函数中，从 `useAppState()` 解构 `selectedConvIds`
2. 定义 `handleBatchDelete` 异步函数：
   - 将 `selectedConvIds` 转为数组 `ids`
   - 对每个 id 调用 `api.deleteConversation(id)`（可用 `Promise.all` 或 `for` 循环）
   - dispatch `{ type: "DELETE_CONVERSATIONS", conversationIds: ids }`
   - 若被删除的 id 中包含 `currentConversationId`，dispatch `{ type: "SET_VIEW", view: "new_chat" }`
3. 将 `handleBatchDelete` 作为 `onBatchDelete` prop 传给 `<Sidebar>`
4. 在删除完成后重新加载会话列表（`api.listConversations()` → dispatch `LOAD_CONVERSATIONS`）以保持与后端同步

**验证：** `cd frontend && npx tsc --noEmit` 全项目编译通过，无类型错误

---

## 执行顺序

```
T1（storage.py）  ──┐
                    ├── 并行，无依赖
T2（routes.py）   ──┘

T3（types.ts） ──── T4（AppContext.tsx）
                        │
T5（client.ts） ────────┤
                        │
T3 ── T6（NavSection.tsx）── 并行
T3 ── T7（MainArea.tsx） ─── 并行

T8（ConversationItem.tsx）── T9（ConversationList.tsx）
                                      │
                     T4 ──────────────┤
                                      │
                           T10（Sidebar.tsx）
                                      │
                     T4 + T5 ──────── T11（App.tsx）
```

所有任务完成后运行 `cd frontend && npx tsc --noEmit` 全量编译通过。
