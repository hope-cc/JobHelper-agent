import { useEffect, useCallback } from "react";
import { AppProvider, useAppState, useAppDispatch } from "./AppContext";
import * as api from "./api/client";
import Sidebar from "./components/Sidebar";
import MainArea from "./components/MainArea";
import type { ConversationSummary } from "./types";

function AppShell() {
  const { view, conversations, currentConversationId, selectedConvIds } =
    useAppState();
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

  const handleBatchDelete = useCallback(async () => {
    const ids = [...selectedConvIds];
    if (ids.length === 0) return;

    // 逐个删除
    const results = await Promise.allSettled(
      ids.map((id) => api.deleteConversation(id))
    );
    const failed = results.filter((r) => r.status === "rejected");
    if (failed.length > 0) {
      console.error("部分会话删除失败", failed);
    }

    // 从 state 中移除
    dispatch({ type: "DELETE_CONVERSATIONS", conversationIds: ids });

    // 若被删会话包含当前查看的会话，回退到新聊天
    if (currentConversationId && ids.includes(currentConversationId)) {
      dispatch({ type: "SET_VIEW", view: "new_chat" });
    }

    // 刷新会话列表以保持与后端同步
    try {
      const list = await api.listConversations();
      dispatch({ type: "LOAD_CONVERSATIONS", conversations: list });
    } catch (err) {
      console.error("刷新会话列表失败:", err);
    }
  }, [selectedConvIds, currentConversationId, dispatch]);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        currentView={view}
        conversations={conversations}
        activeId={currentConversationId}
        onNavigate={handleNavigate}
        onSelectConversation={handleSelectConversation}
        onBatchDelete={handleBatchDelete}
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
