import type { ConversationSummary } from "../types";
import ConversationItem from "./ConversationItem";

interface ConversationListProps {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (conv: ConversationSummary) => void;
}

export default function ConversationList({
  conversations,
  activeId,
  onSelect,
}: ConversationListProps) {
  return (
    <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
      {conversations.length === 0 ? (
        <p className="text-gray-400 text-xs text-center mt-8">暂无会话记录</p>
      ) : (
        conversations.map((conv) => (
          <ConversationItem
            key={conv.id}
            conversation={conv}
            isActive={conv.id === activeId}
            onClick={() => onSelect(conv)}
          />
        ))
      )}
    </div>
  );
}
