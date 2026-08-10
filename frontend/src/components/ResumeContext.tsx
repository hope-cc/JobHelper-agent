import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import type { ResumeState, ResumeAction, Block, Connection } from "../types";

const initialState: ResumeState = {
  resumes: [],
  currentResume: null,
  selectedBlockId: null,
  selectedConnectionId: null,
};

function resumeReducer(state: ResumeState, action: ResumeAction): ResumeState {
  switch (action.type) {
    case "LOAD_RESUMES":
      return { ...state, resumes: action.resumes };

    case "SET_CURRENT_RESUME":
      return {
        ...state,
        currentResume: action.resume,
        selectedBlockId: null,
        selectedConnectionId: null,
      };

    case "ADD_RESUME":
      return {
        ...state,
        resumes: [...state.resumes, action.resume],
        currentResume: action.resume,
        selectedBlockId: null,
        selectedConnectionId: null,
      };

    case "REMOVE_RESUME": {
      const nextResumes = state.resumes.filter((r) => r.id !== action.resumeId);
      const nextCurrent =
        state.currentResume?.id === action.resumeId
          ? null
          : state.currentResume;
      return { ...state, resumes: nextResumes, currentResume: nextCurrent };
    }

    case "UPDATE_RESUME_NAME": {
      if (!state.currentResume) return state;
      return {
        ...state,
        currentResume: { ...state.currentResume, name: action.name },
        resumes: state.resumes.map((r) =>
          r.id === state.currentResume!.id ? { ...r, name: action.name } : r
        ),
      };
    }

    case "ADD_BLOCK": {
      if (!state.currentResume) return state;
      return {
        ...state,
        currentResume: {
          ...state.currentResume,
          blocks: [...state.currentResume.blocks, action.block],
        },
      };
    }

    case "UPDATE_BLOCK": {
      if (!state.currentResume) return state;
      return {
        ...state,
        currentResume: {
          ...state.currentResume,
          blocks: state.currentResume.blocks.map((b) =>
            b.id === action.block.id ? action.block : b
          ),
        },
      };
    }

    case "DELETE_BLOCK": {
      if (!state.currentResume) return state;
      return {
        ...state,
        currentResume: {
          ...state.currentResume,
          blocks: state.currentResume.blocks.filter(
            (b) => b.id !== action.blockId
          ),
          connections: state.currentResume.connections.filter(
            (c) =>
              c.fromBlockId !== action.blockId && c.toBlockId !== action.blockId
          ),
        },
        selectedBlockId:
          state.selectedBlockId === action.blockId
            ? null
            : state.selectedBlockId,
      };
    }

    case "MOVE_BLOCK": {
      if (!state.currentResume) return state;
      return {
        ...state,
        currentResume: {
          ...state.currentResume,
          blocks: state.currentResume.blocks.map((b) =>
            b.id === action.blockId
              ? { ...b, position: action.position }
              : b
          ),
        },
      };
    }

    case "ADD_CONNECTION": {
      if (!state.currentResume) return state;
      return {
        ...state,
        currentResume: {
          ...state.currentResume,
          connections: [
            ...state.currentResume.connections,
            action.connection,
          ],
        },
      };
    }

    case "DELETE_CONNECTION": {
      if (!state.currentResume) return state;
      return {
        ...state,
        currentResume: {
          ...state.currentResume,
          connections: state.currentResume.connections.filter(
            (c) => c.id !== action.connectionId
          ),
        },
        selectedConnectionId:
          state.selectedConnectionId === action.connectionId
            ? null
            : state.selectedConnectionId,
      };
    }

    case "SELECT_BLOCK":
      return {
        ...state,
        selectedBlockId: action.blockId,
        selectedConnectionId: null,
      };

    case "SELECT_CONNECTION":
      return {
        ...state,
        selectedBlockId: null,
        selectedConnectionId: action.connectionId,
      };

    case "CLEAR_SELECTION":
      return {
        ...state,
        selectedBlockId: null,
        selectedConnectionId: null,
      };

    default:
      return state;
  }
}

const ResumeStateContext = createContext<ResumeState | null>(null);
const ResumeDispatchContext = createContext<Dispatch<ResumeAction> | null>(null);

export function ResumeProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(resumeReducer, initialState);
  return (
    <ResumeStateContext.Provider value={state}>
      <ResumeDispatchContext.Provider value={dispatch}>
        {children}
      </ResumeDispatchContext.Provider>
    </ResumeStateContext.Provider>
  );
}

export function useResumeState(): ResumeState {
  const ctx = useContext(ResumeStateContext);
  if (!ctx) throw new Error("useResumeState 必须在 ResumeProvider 内使用");
  return ctx;
}

export function useResumeDispatch(): Dispatch<ResumeAction> {
  const ctx = useContext(ResumeDispatchContext);
  if (!ctx) throw new Error("useResumeDispatch 必须在 ResumeProvider 内使用");
  return ctx;
}
