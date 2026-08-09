import { useEffect, useRef } from "react";
import { useAppState, useAppDispatch } from "../AppContext";
import * as api from "../api/client";
import { parseSSEStream } from "../api/sse";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";

export default function ChatView() {
  const { currentConversationId, messages, isStreaming, conversations } = useAppState();
  const dispatch = useAppDispatch();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 当前会话标题
  const title =
    conversations.find((c) => c.id === currentConversationId)?.title || "对话";

  // 新消息时自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend(content: string) {
    if (!currentConversationId) return;

    try {
      // 添加用户消息
      dispatch({ type: "APPEND_MESSAGE", message: { role: "user", content } });

      // 发送消息
      dispatch({ type: "SET_STREAMING", isStreaming: true });
      const reader = await api.sendMessage(currentConversationId, content);

      await parseSSEStream(reader, {
        onText(delta) {
          dispatch({ type: "UPDATE_LAST_MESSAGE", delta });
        },
        onDone() {
          dispatch({ type: "SET_STREAMING", isStreaming: false });
          // 刷新会话列表（标题可能更新）
          api.listConversations().then((list) => {
            dispatch({ type: "LOAD_CONVERSATIONS", conversations: list });
          });
        },
        onError(err) {
          dispatch({ type: "SET_STREAMING", isStreaming: false });
          console.error("SSE error:", err);
        },
        onToolStart(toolId, toolName) {
          dispatch({ type: "TOOL_START", toolId, toolName });
        },
        onToolDelta(toolId, delta) {
          dispatch({ type: "TOOL_DELTA", toolId, delta });
        },
        onToolEnd(toolId) {
          dispatch({ type: "TOOL_END", toolId });
        },
        onToolResult(toolId, content, isError) {
          dispatch({ type: "TOOL_RESULT", toolId, content, isError });
        },
      });
    } catch (err) {
      dispatch({ type: "SET_STREAMING", isStreaming: false });
      console.error("发送消息失败:", err);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* 标题栏 */}
      <div className="text-center py-3 border-b border-gray-200 bg-white">
        <h2 className="text-sm font-medium text-gray-600 truncate px-4">{title}</h2>
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto">
          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} />
          ))}

          {isStreaming && (
            <p className="text-gray-400 text-sm pl-2">正在输入...</p>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 底部输入框 */}
      <div className="max-w-3xl mx-auto w-full">
        <ChatInput onSend={handleSend} disabled={isStreaming} />
      </div>
    </div>
  );
}
