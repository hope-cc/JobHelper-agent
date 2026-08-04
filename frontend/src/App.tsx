import { useEffect } from "react";
import { AppProvider, useAppState, useAppDispatch } from "./AppContext";
import * as api from "./api/client";
import Sidebar from "./components/Sidebar";
import MainArea from "./components/MainArea";
import type { ConversationSummary } from "./types";

function AppShell() {
  const { view, conversations, currentConversationId } = useAppState();
  const dispatch = useAppDispatch();

  // 初始化：加载会话列表
  useEffect(() => {
    api
      .listConversations()
      .then((list) => dispatch({ type: "LOAD_CONVERSATIONS", conversations: list }))
      .catch((err) => console.error("加载会话列表失败:", err));
  }, [dispatch]);

  function handleNavigate(targetView: typeof view) {
    dispatch({ type: "SET_VIEW", view: targetView });
  }

  function handleSelectConversation(conv: ConversationSummary) {
    // 加载完整的会话消息
    api
      .getConversation(conv.id)
      .then((full) => {
        dispatch({
          type: "SET_CURRENT_CONVERSATION",
          id: full.id,
          messages: full.messages,
        });
      })
      .catch((err) => console.error("加载会话失败:", err));
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        currentView={view}
        conversations={conversations}
        activeId={currentConversationId}
        onNavigate={handleNavigate}
        onSelectConversation={handleSelectConversation}
      />
      <MainArea />
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppShell />
    </AppProvider>
  );
}
