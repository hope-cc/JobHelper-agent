import { useAppDispatch } from "../AppContext";
import * as api from "../api/client";
import { parseSSEStream } from "../api/sse";
import ChatInput from "./ChatInput";

export default function WelcomeScreen() {
  const dispatch = useAppDispatch();

  async function handleSend(content: string) {
    try {
      // 1. 创建新会话
      const conv = await api.createConversation();
      dispatch({
        type: "ADD_CONVERSATION",
        conversation: { id: conv.id, title: conv.title, created_at: conv.created_at },
      });

      // 2. 添加用户消息到界面
      dispatch({ type: "APPEND_MESSAGE", message: { role: "user", content } });

      // 3. 切换到对话视图
      dispatch({
        type: "SET_CURRENT_CONVERSATION",
        id: conv.id,
        messages: [{ role: "user", content }],
      });

      // 4. 发送消息并处理 SSE 流
      dispatch({ type: "SET_STREAMING", isStreaming: true });
      const reader = await api.sendMessage(conv.id, content);

      const assistantMessages: string[] = [];
      await parseSSEStream(reader, {
        onText(delta) {
          assistantMessages.push(delta);
          dispatch({ type: "UPDATE_LAST_MESSAGE", delta });
        },
        onDone() {
          dispatch({ type: "SET_STREAMING", isStreaming: false });
          // 更新侧边栏标题（后端可能已更新）
          api.listConversations().then((list) => {
            dispatch({ type: "LOAD_CONVERSATIONS", conversations: list });
          });
        },
        onError(err) {
          dispatch({ type: "SET_STREAMING", isStreaming: false });
          console.error("SSE error:", err);
        },
      });
    } catch (err) {
      dispatch({ type: "SET_STREAMING", isStreaming: false });
      console.error("发送消息失败:", err);
    }
  }

  return (
    <div className="flex flex-col items-center justify-center h-full">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-800 mb-2">JobHelper</h1>
        <p className="text-gray-500">你的 AI 就业助手</p>
      </div>
      <div className="w-full max-w-2xl px-4">
        <ChatInput onSend={handleSend} placeholder="输入你的求职问题..." />
      </div>
    </div>
  );
}
