# JobHelper 前端 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/api/__init__.py` | 包初始化 |
| 新建 | `src/api/storage.py` | JSON 文件读写 |
| 新建 | `src/api/sse.py` | StreamEvent → SSE 转换 |
| 新建 | `src/api/routes.py` | API 路由定义 |
| 新建 | `src/api/main.py` | FastAPI 入口 + CORS |
| 新建 | `frontend/` 整个目录 | Vite + React + Tailwind 项目 |
| 新建 | `frontend/src/types.ts` | TypeScript 类型定义 |
| 新建 | `frontend/src/api/client.ts` | HTTP + SSE 封装 |
| 新建 | `frontend/src/AppContext.tsx` | 全局状态管理 |
| 新建 | `frontend/src/components/` 下 10 个组件 | UI 组件 |
| 新建 | `frontend/src/App.tsx` | 根布局 |
| 新建 | `frontend/src/main.tsx` | React 入口 |
| 新建 | `data/conversations/` | JSON 存储目录（含 .gitkeep） |

## T1: 创建会话存储模块

**文件：** `src/api/storage.py`
**依赖：** 无
**步骤：**
1. 定义 `DATA_DIR = Path("data/conversations")`
2. 实现 `list_conversations()` — 遍历目录下所有 `.json` 文件，读取 id、title、created_at，按 created_at 倒序返回
3. 实现 `get_conversation(id: str)` — 读取单个 JSON 文件，返回完整对象
4. 实现 `create_conversation()` — 生成 UUID、创建空 JSON 文件（messages=[]），返回会话对象
5. 实现 `add_message(id: str, message)` — 读取文件、追加 message、写回
6. 实现 `update_title(id: str, title: str)` — 读取文件、更新 title、写回

**验证：** 在 Python 交互环境中手动调用各函数，确认 JSON 文件正确创建和读取

## T2: 创建 SSE 适配模块

**文件：** `src/api/sse.py`
**依赖：** 无（仅依赖已有的 `src.llm.types`）
**步骤：**
1. 导入 `StreamEvent`、`TextChunk`、`ThinkingChunk`
2. 实现 `to_sse(event: StreamEvent) -> str` 函数，根据事件类型返回 SSE 格式字符串
   - TextChunk → `event: text\ndata: {"delta":"..."}\n\n`
   - ThinkingChunk → `event: thinking\ndata: {"delta":"..."}\n\n`
   - 其他事件类型返回空字符串
3. 实现 `sse_stream(stream) -> AsyncGenerator[str, None]` — 遍历 stream，对每个 event 调用 to_sse，yield 结果，最后 yield done 事件

**验证：** 构造 mock TextChunk，调用 to_sse，确认输出格式正确

## T3: 创建 API 路由

**文件：** `src/api/routes.py`
**依赖：** T1, T2，已有 `src.llm.factory` 和 `src.config.loader`
**步骤：**
1. 创建 `APIRouter(prefix="/api")`
2. `GET /conversations` — 调用 storage.list_conversations() 返回 JSON
3. `POST /conversations` — 调用 storage.create_conversation() 返回 JSON
4. `GET /conversations/{id}` — 调用 storage.get_conversation(id)，不存在返回 404
5. `POST /conversations/{id}/messages` — 读取 body 中的 `content`，追加 user 消息到存储；构建 messages 历史；调用 LLM client.stream()；返回 StreamingResponse，content_type="text/event-stream"，内容由 sse_stream() 生成；流结束后将 assistant 回复追加到存储；如果是首条消息，自动更新会话标题

**验证：** 用 curl 测试每个端点，确认 JSON 响应正确；用 curl 测试消息发送端点，确认 SSE 流式输出

## T4: 创建 FastAPI 入口

**文件：** `src/api/main.py`
**依赖：** T3
**步骤：**
1. 创建 FastAPI app 实例
2. 添加 CORS 中间件（允许 `*` 来源）
3. 挂载 T3 的路由
4. 实现 `main()` 函数：加载配置、选择供应商、创建 LLM 客户端、以 uvicorn 启动
5. 实现 `__main__` 入口

**验证：** `python -m src.api.main` 启动服务，浏览器访问 `http://localhost:8000/api/conversations` 返回 `[]`

## T5: 搭建前端项目

**文件：** `frontend/` 下所有配置文件
**依赖：** 无
**步骤：**
1. 使用 `npm create vite@latest frontend -- --template react-ts` 创建项目（手动操作，需用户执行）
2. 安装 Tailwind CSS 及其 Vite 插件: `npm install -D tailwindcss @tailwindcss/vite`
3. 配置 `vite.config.ts`：添加 tailwindcss 插件、配置 `/api` 代理到 `http://localhost:8000`
4. 配置 `tailwind.config.js`：content 路径指向 `./src/**/*.{ts,tsx}`
5. 在 `index.css` 中添加 Tailwind 指令
6. 清理 Vite 默认生成的无用文件（App.css、assets 等）

**验证：** `npm run dev` 启动，浏览器打开显示空白页面无报错

## T6: 定义前端类型

**文件：** `frontend/src/types.ts`
**依赖：** 无
**步骤：**
1. 定义 `Message` 接口：role（"user" | "assistant"）、content（string）
2. 定义 `Conversation` 接口：id、title、created_at（string）、messages（Message[]）
3. 定义 `ConversationSummary` 类型：不含 messages 的 Conversation（id、title、created_at）
4. 定义 `ViewType`：`"new_chat" | "resume" | "progress" | "conversation"`
5. 定义 `AppState` 接口：view、conversations、currentConversationId、messages、isStreaming

**验证：** TypeScript 编译无报错（`npx tsc --noEmit`）

## T7: 创建前端 API 客户端

**文件：** `frontend/src/api/client.ts`
**依赖：** T6
**步骤：**
1. 实现 `listConversations(): Promise<ConversationSummary[]>`
2. 实现 `getConversation(id: string): Promise<Conversation>`
3. 实现 `createConversation(): Promise<Conversation>`
4. 实现 `sendMessage(id: string, content: string): Promise<ReadableStreamDefaultReader>` — POST 请求，返回 reader 用于流式读取 SSE

**验证：** 后端运行时，在浏览器 console 中调用这些函数确认能获取数据

## T8: 创建全局状态管理

**文件：** `frontend/src/AppContext.tsx`
**依赖：** T6
**步骤：**
1. 创建 `AppContext` 和 `AppDispatchContext`
2. 定义 reducer actions：`SET_VIEW`、`LOAD_CONVERSATIONS`、`SET_CURRENT_CONVERSATION`、`APPEND_MESSAGE`、`UPDATE_LAST_MESSAGE`、`ADD_CONVERSATION`、`SET_STREAMING`
3. 实现 `AppProvider` 组件：使用 `useReducer`，初始化 state
4. 导出 `useAppState()` 和 `useAppDispatch()` hooks

**验证：** TypeScript 编译无报错

## T9: 创建占位页面组件

**文件：** `frontend/src/components/PlaceholderPage.tsx`
**依赖：** 无
**步骤：**
1. 接收 `title` prop（如"简历管理"或"投递进度"）
2. 渲染居中文本："{title} — 该功能将在后续版本开发"

**验证：** 在 App 中临时引用，确认渲染正确

## T10: 创建侧边栏组件

**文件：** `frontend/src/components/NavSection.tsx`、`ConversationItem.tsx`、`ConversationList.tsx`、`Sidebar.tsx`
**依赖：** T6, T8
**步骤：**
1. **NavSection**：渲染三个导航按钮（新聊天、简历管理、投递进度），当前选中的加高亮样式。点击时 dispatch SET_VIEW。
2. **ConversationItem**：渲染单条会话标题（截断超长标题），点击时 dispatch 加载该会话。当前选中的加高亮。
3. **ConversationList**：接收 conversations 数组，map 为 ConversationItem 列表。超出高度可滚动。
4. **Sidebar**：组合 NavSection + 分隔线 + ConversationList。固定宽度 w-1/7，全高。

**验证：** 在 App 中引用 Sidebar，确认三个导航可点击、会话列表可显示

## T11: 创建聊天输入与消息气泡

**文件：** `frontend/src/components/ChatInput.tsx`、`frontend/src/components/MessageBubble.tsx`
**依赖：** T6
**步骤：**
1. **ChatInput**：textarea + 发送按钮。支持 Enter 发送（Shift+Enter 换行）。接收 `onSend(content: string)` prop 和 `disabled` prop（流式输出中禁用）。发送后清空输入框。
2. **MessageBubble**：接收 `message: Message` prop。user 消息右对齐（浅蓝背景），assistant 消息左对齐（灰色背景）。支持简单的文本换行渲染（用 `whitespace-pre-wrap`）。

**验证：** 在 App 中临时引用，输入文本点击发送，确认 onSend 被调用且收到正确内容

## T12: 创建欢迎页

**文件：** `frontend/src/components/WelcomeScreen.tsx`
**依赖：** T11, T7, T8
**步骤：**
1. 居中渲染 ChatInput
2. 用户发送时：调用 `createConversation()` 创建新会话，再调用 `sendMessage(id, content)`；dispatch ADD_CONVERSATION 和 SET_VIEW 到 conversation 视图；处理 SSE 流式响应
3. SSE 流处理逻辑：使用 reader 逐行读取，解析 `event:` 和 `data:` 行；event=text 时 dispatch APPEND_MESSAGE 或 UPDATE_LAST_MESSAGE；event=done 时标记流结束，调用 API 获取最终完整消息

**验证：** 发送消息后能流式看到 LLM 回复，侧边栏自动新增会话

## T13: 创建聊天视图

**文件：** `frontend/src/components/ChatView.tsx`
**依赖：** T11, T7, T8
**步骤：**
1. 顶部显示会话标题
2. 中间区域渲染消息列表（MessageBubble 列表），可滚动，新消息自动滚动到底部
3. 底部固定 ChatInput
4. 发送消息逻辑与 T12 类似，但不创建新会话（直接使用 currentConversationId）
5. 支持流式响应中显示"正在输入..."状态

**验证：** 在已有会话中发送消息，能流式看到回复，上下文正确传递

## T14: 创建主区域组件

**文件：** `frontend/src/components/MainArea.tsx`
**依赖：** T12, T13, T9, T8
**步骤：**
1. 读取 `useAppState().view`
2. view === "new_chat" → 渲染 WelcomeScreen
3. view === "conversation" → 渲染 ChatView
4. view === "resume" → 渲染 PlaceholderPage("简历管理")
5. view === "progress" → 渲染 PlaceholderPage("投递进度")

**验证：** 切换导航项，右侧内容正确切换

## T15: 组装根组件

**文件：** `frontend/src/App.tsx`、`frontend/src/main.tsx`
**依赖：** T10, T14, T8
**步骤：**
1. **App.tsx**：AppProvider 包裹 flex 容器；左侧 Sidebar（w-1/7），右侧 MainArea（flex-1）；初始化时 dispatch LOAD_CONVERSATIONS
2. **main.tsx**：ReactDOM.createRoot，渲染 App
3. 点击历史会话时：dispatch SET_CURRENT_CONVERSATION，调用 API 获取完整会话，dispatch 消息列表

**验证：** 完整流程：打开页面 → 新聊天 → 发消息 → 查看流式回复 → 点击侧边栏会话 → 查看历史 → 切换导航

## 执行顺序

```
T1 → T2 → T3 → T4（后端完成）
                  ↘
T5 → T6 → T7 → T8 → T9 → T10 → T11 → T12 → T13 → T14 → T15（前端完成）
                                              （T9/T10/T11 可并行）
```
