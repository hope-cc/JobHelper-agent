import type { ViewType, ConversationSummary } from "../types";
import { useAppState, useAppDispatch } from "../AppContext";
import NavSection from "./NavSection";
import ConversationList from "./ConversationList";

interface SidebarProps {
  currentView: ViewType;
  conversations: ConversationSummary[];
  activeId: string | null;
  onNavigate: (view: ViewType) => void;
  onSelectConversation: (conv: ConversationSummary) => void;
  onBatchDelete: () => void;
}

export default function Sidebar({
  currentView,
  conversations,
  activeId,
  onNavigate,
  onSelectConversation,
  onBatchDelete,
}: SidebarProps) {
  const { batchDeleteMode, selectedConvIds } = useAppState();
  const dispatch = useAppDispatch();

  function handleToggleBatchDelete() {
    dispatch({ type: "TOGGLE_BATCH_DELETE" });
  }

  function handleToggleSelect(id: string) {
    dispatch({ type: "TOGGLE_SELECT_CONVERSATION", conversationId: id });
  }

  return (
    <aside className="w-1/7 min-w-[200px] max-w-[280px] h-screen flex flex-col bg-gray-50 border-r border-gray-200">
      {/* 功能导航区 */}
      <div className="p-3 pt-4">
        <h1 className="text-base font-bold text-gray-800 px-2 mb-3">
          JobHelper
        </h1>
        <NavSection currentView={currentView} onNavigate={onNavigate} />
      </div>

      {/* 分隔线 */}
      <div className="mx-3 border-t border-gray-200" />

      {/* 会话历史区 */}
      <div className="flex-1 flex flex-col min-h-0 p-3">
        <ConversationList
          conversations={conversations}
          activeId={activeId}
          onSelect={onSelectConversation}
          batchDeleteMode={batchDeleteMode}
          selectedIds={selectedConvIds}
          onToggleSelect={handleToggleSelect}
          onDelete={onBatchDelete}
          onToggleBatchDelete={handleToggleBatchDelete}
        />
      </div>
    </aside>
  );
}
