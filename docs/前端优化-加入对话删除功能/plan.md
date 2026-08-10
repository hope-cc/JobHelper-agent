# 个人信息管理导航项 + 批量删除会话 Plan

## 架构概览

本次改动涉及前端 7 个文件和后端 2 个文件。

**前端**：在现有 `useReducer` 状态管理框架内扩展。新增 `batchDeleteMode` 和 `selectedConvIds` 两个状态字段，以及对应的 `TOGGLE_BATCH_DELETE`、`TOGGLE_SELECT_CONVERSATION`、`DELETE_CONVERSATIONS` 三个 action。批量删除的状态和交互逻辑集中在 `ConversationList` 组件中，`ConversationItem` 接收 `showCheckbox` 和 `isSelected` props 来渲染勾选框。

**后端**：在 `storage.py` 新增 `delete_conversation()` 函数（删除 JSON 文件），在 `routes.py` 新增 `DELETE /api/conversations/{conversation_id}` 路由。

## 核心数据结构

### AppState 新增字段（types.ts）

```typescript
export interface AppState {
  // ...现有字段保持不变
  batchDeleteMode: boolean;
  selectedConvIds: Set<string>;
}
```

### AppAction 新增 action（types.ts）

```typescript
export type AppAction =
  // ...现有 action 保持不变
  | { type: "TOGGLE_BATCH_DELETE" }
  | { type: "TOGGLE_SELECT_CONVERSATION"; conversationId: string }
  | { type: "DELETE_CONVERSATIONS"; conversationIds: string[] };
```

### ConversationList 新增 props

```typescript
interface ConversationListProps {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (conv: ConversationSummary) => void;
  batchDeleteMode: boolean;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  onDelete: () => void;
}
```

### ConversationItem 新增 props

```typescript
interface ConversationItemProps {
  conversation: ConversationSummary;
  isActive: boolean;
  onClick: () => void;
  showCheckbox: boolean;
  isSelected: boolean;
  onToggleSelect: () => void;
}
```

### 后端 delete_conversation 函数

```python
def delete_conversation(conversation_id: str) -> bool:
    """删除指定会话的 JSON 文件。文件不存在时返回 False（幂等，不抛异常）。"""
```

### 后端 DELETE 路由

```
DELETE /api/conversations/{conversation_id} → 204 No Content
```

## 模块设计

### types.ts（类型扩展）
**职责**：定义 ViewType 新增字面量、AppState 新增字段、AppAction 新增 action 类型
**改动**：ViewType 添加 `"profile"`；AppState 添加 `batchDeleteMode` 和 `selectedConvIds`；AppAction 添加三个新 action
**依赖**：无

### AppContext.tsx（状态管理扩展）
**职责**：在 reducer 中处理三个新 action；在 initialState 中初始化新字段
**改动**：initialState 添加新字段；reducer 添加三个 case
**依赖**：types.ts

### NavSection.tsx（导航项扩展）
**职责**：在 NAV_ITEMS 数组中新增"个人信息管理"
**改动**：添加 `{ key: "profile", label: "个人信息管理", icon: "👤" }`
**依赖**：types.ts

### MainArea.tsx（视图路由扩展）
**职责**：为 `"profile"` 视图添加路由分支
**改动**：添加 `case "profile": return <PlaceholderPage title="个人信息管理" />;`
**依赖**：PlaceholderPage.tsx

### ConversationItem.tsx（勾选框）
**职责**：在批量删除模式下渲染勾选框，点击勾选框触发选择而非导航
**改动**：新增三个 props；条件渲染 checkbox；stopPropagation 隔离
**依赖**：无新增依赖

### ConversationList.tsx（批量删除控制）
**职责**：承载批量删除开关、删除按钮，向 ConversationItem 传递勾选状态
**改动**：新增四个 props；标题旁添加 Toggle；条件渲染删除按钮和勾选框
**依赖**：ConversationItem

### Sidebar.tsx（props 透传）
**职责**：将批量删除相关的 state 和 dispatch 透传给 ConversationList
**改动**：解构新增 state 字段；定义三个回调；透传所有 props
**依赖**：ConversationList、AppContext

### App.tsx（删除逻辑编排）
**职责**：实现 handleBatchDelete 回调
**改动**：遍历 selectedConvIds 调用 API；dispatch DELETE_CONVERSATIONS；必要时 SET_VIEW
**依赖**：api/client.ts、AppContext

### storage.py（删除存储函数）
**职责**：实现 delete_conversation() 函数
**改动**：新增函数，os.remove JSON 文件，FileNotFoundError 时返回 False
**依赖**：无新增依赖

### routes.py（删除路由）
**职责**：注册 DELETE 路由
**改动**：新增 handler，调用 storage.delete_conversation()，返回 204
**依赖**：storage.py

## 模块交互

### 新增导航项流程
```
用户点击"个人信息管理"
  → NavSection.onNavigate("profile")
    → dispatch({ type: "SET_VIEW", view: "profile" })
      → MainArea case "profile" → <PlaceholderPage />
```

### 批量删除流程
```
用户打开批量删除开关
  → dispatch TOGGLE_BATCH_DELETE
    → ConversationList 收到 batchDeleteMode=true → 渲染勾选框+删除按钮

用户勾选会话
  → ConversationItem checkbox onClick → e.stopPropagation()
    → dispatch TOGGLE_SELECT_CONVERSATION

用户点击删除
  → AppShell.handleBatchDelete()
    → 遍历 selectedConvIds → api.deleteConversation(id)
      → DELETE /api/conversations/{id}
        → storage.delete_conversation(id)
    → dispatch DELETE_CONVERSATIONS
    → 若被删ID含当前会话 → dispatch SET_VIEW "new_chat"
```

## 文件组织

```
frontend/src/
├── types.ts                    — 修改：ViewType、AppState、AppAction 扩展
├── AppContext.tsx              — 修改：initialState、reducer 扩展
├── App.tsx                     — 修改：handleBatchDelete 回调实现
├── components/
│   ├── Sidebar.tsx             — 修改：props 透传
│   ├── NavSection.tsx          — 修改：NAV_ITEMS 新增一项
│   ├── MainArea.tsx            — 修改：新增 case "profile"
│   ├── ConversationList.tsx    — 修改：新增批量删除 UI 和逻辑
│   └── ConversationItem.tsx    — 修改：新增勾选框
└── api/
    └── client.ts               — 修改：新增 deleteConversation()

src/api/
├── storage.py                  — 修改：新增 delete_conversation()
└── routes.py                   — 修改：新增 DELETE 路由
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 勾选状态存储 | `Set<string>` 在 AppState 中 | O(1) 查找，天然去重 |
| 批量删除实现 | 前端逐个调用 DELETE 接口 | 后端单文件删除，无需事务性 |
| "删除"按钮禁用 | size===0 时 disabled | 清晰反馈优于点击后无响应 |
| 删除后模式保持 | 保持批量删除模式 | 用户可能分批删除多组 |
| 当前会话被删处理 | reducer + 额外 SET_VIEW | 避免残留数据 |
| 勾选与导航隔离 | stopPropagation | 勾选不影响会话查看 |
| 后端幂等 | 文件不存在返回 False | 避免一次双击导致 500 |
