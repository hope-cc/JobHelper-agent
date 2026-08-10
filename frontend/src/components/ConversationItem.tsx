import type { ConversationSummary } from "../types";

interface ConversationItemProps {
  conversation: ConversationSummary;
  isActive: boolean;
  onClick: () => void;
  showCheckbox: boolean;
  isSelected: boolean;
  onToggleSelect: () => void;
}

export default function ConversationItem({
  conversation,
  isActive,
  onClick,
  showCheckbox,
  isSelected,
  onToggleSelect,
}: ConversationItemProps) {
  return (
    <button
      className={`w-full text-left px-3 py-2.5 rounded-lg text-sm truncate transition flex items-center ${
        isActive
          ? "bg-blue-50 text-blue-700 font-medium"
          : "text-gray-600 hover:bg-gray-100"
      }`}
      onClick={onClick}
      title={conversation.title}
    >
      {showCheckbox && (
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggleSelect}
          onClick={(e) => e.stopPropagation()}
          className="mr-2 flex-shrink-0"
        />
      )}
      <span className="truncate">{conversation.title}</span>
    </button>
  );
}
