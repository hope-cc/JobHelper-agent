/** 单条消息 */
export interface Message {
  role: "user" | "assistant";
  content: string;
}

/** 完整会话（含消息列表） */
export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  messages: Message[];
}

/** 会话摘要（不含消息列表） */
export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
}

/** 当前视图类型 */
export type ViewType = "new_chat" | "resume" | "progress" | "conversation";

/** 全局应用状态 */
export interface AppState {
  view: ViewType;
  conversations: ConversationSummary[];
  currentConversationId: string | null;
  messages: Message[];
  isStreaming: boolean;
}

/** Reducer action 联合类型 */
export type AppAction =
  | { type: "SET_VIEW"; view: ViewType }
  | { type: "LOAD_CONVERSATIONS"; conversations: ConversationSummary[] }
  | { type: "ADD_CONVERSATION"; conversation: ConversationSummary }
  | { type: "SET_CURRENT_CONVERSATION"; id: string; messages: Message[] }
  | { type: "APPEND_MESSAGE"; message: Message }
  | { type: "UPDATE_LAST_MESSAGE"; delta: string }
  | { type: "SET_STREAMING"; isStreaming: boolean };
