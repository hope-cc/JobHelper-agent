import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import type { AppState, AppAction } from "./types";

const initialState: AppState = {
  view: "new_chat",
  conversations: [],
  currentConversationId: null,
  messages: [],
  isStreaming: false,
};

function reducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "SET_VIEW":
      return {
        ...state,
        view: action.view,
        ...(action.view !== "conversation"
          ? { currentConversationId: null, messages: [] }
          : {}),
      };

    case "LOAD_CONVERSATIONS":
      return { ...state, conversations: action.conversations };

    case "ADD_CONVERSATION":
      return {
        ...state,
        conversations: [action.conversation, ...state.conversations],
      };

    case "SET_CURRENT_CONVERSATION":
      return {
        ...state,
        view: "conversation",
        currentConversationId: action.id,
        messages: action.messages,
      };

    case "APPEND_MESSAGE":
      return { ...state, messages: [...state.messages, action.message] };

    case "UPDATE_LAST_MESSAGE": {
      const msgs = [...state.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, content: last.content + action.delta };
      } else {
        msgs.push({ role: "assistant", content: action.delta });
      }
      return { ...state, messages: msgs };
    }

    case "SET_STREAMING":
      return { ...state, isStreaming: action.isStreaming };

    default:
      return state;
  }
}

const StateContext = createContext<AppState | null>(null);
const DispatchContext = createContext<Dispatch<AppAction> | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <StateContext.Provider value={state}>
      <DispatchContext.Provider value={dispatch}>
        {children}
      </DispatchContext.Provider>
    </StateContext.Provider>
  );
}

export function useAppState(): AppState {
  const ctx = useContext(StateContext);
  if (!ctx) throw new Error("useAppState 必须在 AppProvider 内使用");
  return ctx;
}

export function useAppDispatch(): Dispatch<AppAction> {
  const ctx = useContext(DispatchContext);
  if (!ctx) throw new Error("useAppDispatch 必须在 AppProvider 内使用");
  return ctx;
}
