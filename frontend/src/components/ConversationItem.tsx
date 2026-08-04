import type { ConversationSummary } from "../types";

interface ConversationItemProps {
  conversation: ConversationSummary;
  isActive: boolean;
  onClick: () => void;
}

export default function ConversationItem({
  conversation,
  isActive,
  onClick,
}: ConversationItemProps) {
  return (
    <button
      className={`w-full text-left px-3 py-2.5 rounded-lg text-sm truncate transition ${
        isActive
          ? "bg-blue-50 text-blue-700 font-medium"
          : "text-gray-600 hover:bg-gray-100"
      }`}
      onClick={onClick}
      title={conversation.title}
    >
      {conversation.title}
    </button>
  );
}
