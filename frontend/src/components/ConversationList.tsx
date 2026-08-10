import type { ConversationSummary } from "../types";
import ConversationItem from "./ConversationItem";

interface ConversationListProps {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (conv: ConversationSummary) => void;
  batchDeleteMode: boolean;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  onDelete: () => void;
  onToggleBatchDelete: () => void;
}

export default function ConversationList({
  conversations,
  activeId,
  onSelect,
  batchDeleteMode,
  selectedIds,
  onToggleSelect,
  onDelete,
  onToggleBatchDelete,
}: ConversationListProps) {
  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* 标题行 + 批量删除开关 */}
      <div className="flex items-center justify-between px-2 mb-1">
        <p className="text-xs text-gray-400 font-medium uppercase tracking-wider">
          聊天记录
        </p>
        <button
          onClick={onToggleBatchDelete}
          className={`text-xs px-2 py-0.5 rounded transition ${
            batchDeleteMode
              ? "bg-red-100 text-red-600"
              : "text-gray-400 hover:text-gray-600"
          }`}
        >
          {batchDeleteMode ? "退出批量" : "批量删除"}
        </button>
      </div>

      {/* 删除按钮（批量删除模式下） */}
      {batchDeleteMode && (
        <div className="px-2 mb-2">
          <button
            onClick={onDelete}
            disabled={selectedIds.size === 0}
            className={`w-full py-1.5 rounded text-sm font-medium transition ${
              selectedIds.size === 0
                ? "bg-gray-200 text-gray-400 cursor-not-allowed"
                : "bg-red-500 text-white hover:bg-red-600"
            }`}
          >
            删除{selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}
          </button>
        </div>
      )}

      {/* 会话列表 */}
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
              showCheckbox={batchDeleteMode}
              isSelected={selectedIds.has(conv.id)}
              onToggleSelect={() => onToggleSelect(conv.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
