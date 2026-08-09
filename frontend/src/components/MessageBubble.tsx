import type { Message } from "../types";
import ToolCallCard from "./ToolCallCard";

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div className={`max-w-[75%] ${isUser ? "" : ""}`}>
        {/* 工具调用卡片（助手消息头部展示） */}
        {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mb-2 space-y-1">
            {message.toolCalls.map((tc) => (
              <ToolCallCard key={tc.toolId} toolCall={tc} />
            ))}
          </div>
        )}

        {/* 消息正文 */}
        {message.content && (
          <div
            className={`rounded-2xl px-4 py-3 whitespace-pre-wrap break-words ${
              isUser
                ? "bg-blue-500 text-white rounded-br-md"
                : "bg-gray-100 text-gray-800 rounded-bl-md"
            }`}
          >
            {message.content}
          </div>
        )}
      </div>
    </div>
  );
}
