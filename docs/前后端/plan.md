# JobHelper 前端 Plan

## 架构概览

项目分为两个独立运行的服务：

**后端服务（FastAPI）** — 在现有 `src/` 基础上新增 API 层。
负责会话管理、JSON 文件读写、LLM 调用，通过 SSE 推送流式回复。

**前端服务（Vite dev server）** — 全新 React SPA。
负责 UI 渲染、用户交互、通过 HTTP/SSE 与后端通信。

开发时两者独立运行，前端通过 Vite proxy 将 `/api` 请求转发到后端。

## 核心数据结构

### Conversation（会话 — 后端 JSON 存储格式）

每个会话一个文件，存储在 `data/conversations/{id}.json`：

```
{
  "id": "uuid-string",
  "title": "首条用户消息的前30个字符",
  "created_at": "2024-08-04T12:00:00Z",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

### API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/conversations` | 返回会话摘要列表（id, title, created_at），不含 messages |
| POST | `/api/conversations` | 创建空会话，返回会话对象 |
| GET | `/api/conversations/{id}` | 返回完整会话（含 messages 数组） |
| POST | `/api/conversations/{id}/messages` | 发送用户消息，返回 SSE 流（text/event-stream） |

### SSE 事件格式

```
event: text
data: {"delta": "回复文本片段"}

event: thinking
data: {"delta": "思考过程片段"}

event: done
data: {}
```

### 前端类型定义 (TypeScript)

```typescript
interface Conversation {
  id: string;
  title: string;
  created_at: string;
  messages: Message[];
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

type ViewType = "new_chat" | "resume" | "progress" | "conversation";
```

## 模块设计

### 后端模块

#### 模块 A: API 路由 (`src/api/routes.py`)
**职责：** 定义 4 个 HTTP 端点，解析请求参数，委托给存储层和 LLM 层
**对外接口：** FastAPI APIRouter，挂载到 `/api` 前缀
**依赖：** 存储层、LLM 客户端工厂

#### 模块 B: 会话存储 (`src/api/storage.py`)
**职责：** JSON 文件的读写。提供 `list_all()`、`get_by_id()`、`create()`、`add_message()`、`update_title()`
**对外接口：** 纯 async 函数，不依赖 FastAPI
**依赖：** 无（仅标准库 json + pathlib）

#### 模块 C: SSE 适配器 (`src/api/sse.py`)
**职责：** 将现有 `StreamEvent` 转换为 SSE 格式输出
**对外接口：** `sse_stream(stream: AsyncIterator[StreamEvent]) -> AsyncGenerator[str, None]`
**依赖：** `src.llm.types`

#### 模块 D: 入口 (`src/api/main.py`)
**职责：** 创建 FastAPI app，挂载路由、CORS 中间件、启动 uvicorn
**依赖：** 路由模块

### 前端模块

#### 模块 E: 应用入口 (`frontend/src/App.tsx`)
**职责：** 顶层布局。左侧 Sidebar（w-1/7），右侧 MainArea（flex-1）。
通过 React Context 管理全局状态（当前视图、会话列表、当前会话）。
**依赖：** Sidebar、MainArea、AppContext

#### 模块 F: 侧边栏 (`frontend/src/components/Sidebar.tsx`)
**职责：** 渲染导航区 + 会话历史列表。接收当前视图和会话列表，响应用户点击。
**依赖：** NavSection、ConversationList

#### 模块 G: 主区域 (`frontend/src/components/MainArea.tsx`)
**职责：** 根据当前视图类型切换渲染不同子组件。
**依赖：** WelcomeScreen、ChatView、PlaceholderPage

#### 模块 H: 欢迎页 (`frontend/src/components/WelcomeScreen.tsx`)
**职责：** 居中显示输入框。提交后调用 API 创建会话并发送消息，切换视图。
**依赖：** ChatInput

#### 模块 I: 聊天视图 (`frontend/src/components/ChatView.tsx`)
**职责：** 可滚动的消息列表 + 底部输入框。支持 SSE 流式接收。
**依赖：** MessageBubble、ChatInput、SSE 解析逻辑

#### 模块 J: 占位页 (`frontend/src/components/PlaceholderPage.tsx`)
**职责：** 显示"该功能将在后续版本开发"提示
**依赖：** 无

#### 模块 K: API 客户端 (`frontend/src/api/client.ts`)
**职责：** 封装 fetch 调用，提供 `listConversations()`、`getConversation(id)`、`createConversation()`、`sendMessage(id, content)` 四个函数。`sendMessage` 返回 ReadableStream 用于 SSE 解析。
**依赖：** 无（仅 fetch）

## 文件组织

```
JobHelper-agent/
├── src/
│   ├── llm/                    # 已有，不动
│   ├── chat/                   # 已有，不动
│   ├── config/                 # 已有，不动
│   ├── cli/                    # 已有，不动
│   └── api/
│       ├── __init__.py
│       ├── main.py             # FastAPI app 入口
│       ├── routes.py           # API 路由定义
│       ├── storage.py          # JSON 文件存储
│       └── sse.py              # SSE 流式适配
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── src/
│       ├── main.tsx            # React 入口
│       ├── App.tsx             # 根组件 + 布局
│       ├── AppContext.tsx      # 全局状态 (Context)
│       ├── types.ts            # TypeScript 类型
│       ├── api/
│       │   └── client.ts       # HTTP + SSE 封装
│       └── components/
│           ├── Sidebar.tsx
│           ├── NavSection.tsx
│           ├── ConversationList.tsx
│           ├── ConversationItem.tsx
│           ├── MainArea.tsx
│           ├── WelcomeScreen.tsx
│           ├── ChatView.tsx
│           ├── ChatInput.tsx
│           ├── MessageBubble.tsx
│           └── PlaceholderPage.tsx
└── data/
    └── conversations/          # JSON 文件存储目录
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 前端路由 | React Context 状态切换，不用 React Router | 只有 4 个视图，URL 路由无必要，状态切换更简单 |
| 状态管理 | React Context + useReducer | 状态简单（当前视图 + 会话列表），无需引入 Redux/Zustand |
| SSE vs WebSocket | SSE | 单向流式推送足够，SSE 实现更简单，FastAPI 原生支持 |
| 流式解析 | Fetch API + ReadableStream | 浏览器原生支持，不引入 EventSource（POST 请求受限） |
| 后端集成 LangGraph | 先行跳过，直接调用 client.stream() | LangGraph 图目前仅是单节点 scaffold，与 CLI 逻辑相同，后续迭代再接入 |
| 存储目录 | `data/conversations/` | 独立于源码，方便备份和清理 |
