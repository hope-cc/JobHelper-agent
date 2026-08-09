import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import type { AppState, AppAction, ToolCallState } from "./types";

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

    case "TOOL_START": {
      const msgsStart = [...state.messages];
      const lastStart = msgsStart[msgsStart.length - 1];
      const newTc: ToolCallState = {
        toolId: action.toolId,
        toolName: action.toolName,
        argsJson: "",
        result: null,
        status: "running",
      };
      if (lastStart && lastStart.role === "assistant") {
        msgsStart[msgsStart.length - 1] = {
          ...lastStart,
          toolCalls: [...(lastStart.toolCalls || []), newTc],
        };
      } else {
        msgsStart.push({ role: "assistant", content: "", toolCalls: [newTc] });
      }
      return { ...state, messages: msgsStart };
    }

    case "TOOL_DELTA": {
      const msgsDelta = [...state.messages];
      const lastDelta = msgsDelta[msgsDelta.length - 1];
      if (lastDelta && lastDelta.role === "assistant" && lastDelta.toolCalls) {
        const tcs = lastDelta.toolCalls.map((tc) =>
          tc.toolId === action.toolId
            ? { ...tc, argsJson: tc.argsJson + action.delta }
            : tc
        );
        msgsDelta[msgsDelta.length - 1] = { ...lastDelta, toolCalls: tcs };
      }
      return { ...state, messages: msgsDelta };
    }

    case "TOOL_END": {
      const msgsEnd = [...state.messages];
      const lastEnd = msgsEnd[msgsEnd.length - 1];
      if (lastEnd && lastEnd.role === "assistant" && lastEnd.toolCalls) {
        const tcs = lastEnd.toolCalls.map((tc) =>
          tc.toolId === action.toolId ? { ...tc, status: "done" as const } : tc
        );
        msgsEnd[msgsEnd.length - 1] = { ...lastEnd, toolCalls: tcs };
      }
      return { ...state, messages: msgsEnd };
    }

    case "TOOL_RESULT": {
      const msgsResult = [...state.messages];
      const lastResult = msgsResult[msgsResult.length - 1];
      if (lastResult && lastResult.role === "assistant" && lastResult.toolCalls) {
        const tcs = lastResult.toolCalls.map((tc) =>
          tc.toolId === action.toolId
            ? {
                ...tc,
                result: action.content,
                status: action.isError ? ("error" as const) : ("done" as const),
              }
            : tc
        );
        msgsResult[msgsResult.length - 1] = { ...lastResult, toolCalls: tcs };
      }
      return { ...state, messages: msgsResult };
    }

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
