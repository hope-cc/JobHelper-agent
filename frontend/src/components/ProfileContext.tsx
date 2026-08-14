import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import type {
  BasicFieldSchema,
  PersonalProfile,
  ProfileEntry,
  ProfileSectionKey,
} from "../types";
import { emptyProfile } from "./profile/profileFieldConfigs";

type ProfileAction =
  | { type: "LOAD_PROFILE"; profile: PersonalProfile }
  | { type: "SET_BASIC_FIELD"; key: string; value: string }
  | { type: "ADD_BASIC_FIELD"; schema: BasicFieldSchema }
  | { type: "RENAME_BASIC_FIELD"; key: string; label: string }
  | { type: "DELETE_BASIC_FIELD"; key: string }
  | { type: "MOVE_BASIC_FIELD"; fromIndex: number; toIndex: number }
  | { type: "ADD_ENTRY"; section: ProfileSectionKey; entry: ProfileEntry }
  | {
      type: "SET_ENTRY_FIELD";
      section: ProfileSectionKey;
      entryId: string;
      key: string;
      value: string;
    }
  | { type: "DELETE_ENTRY"; section: ProfileSectionKey; entryId: string }
  | { type: "SET_SELF_EVAL"; value: string }
  | { type: "TOGGLE_MASKED_FIELD"; key: string; checked: boolean };

function profileReducer(
  state: PersonalProfile,
  action: ProfileAction
): PersonalProfile {
  switch (action.type) {
    case "LOAD_PROFILE":
      return action.profile;

    case "SET_BASIC_FIELD":
      return {
        ...state,
        basic_info: { ...state.basic_info, [action.key]: action.value },
      };

    case "ADD_BASIC_FIELD":
      return {
        ...state,
        basic_fields_schema: [...state.basic_fields_schema, action.schema],
      };

    case "RENAME_BASIC_FIELD":
      return {
        ...state,
        basic_fields_schema: state.basic_fields_schema.map((f) =>
          f.key === action.key ? { ...f, label: action.label } : f
        ),
      };

    case "DELETE_BASIC_FIELD": {
      const { [action.key]: _removed, ...restInfo } = state.basic_info;
      return {
        ...state,
        basic_fields_schema: state.basic_fields_schema.filter(
          (f) => f.key !== action.key
        ),
        basic_info: restInfo,
        masked_basic_fields: state.masked_basic_fields.filter(
          (k) => k !== action.key
        ),
      };
    }

    case "MOVE_BASIC_FIELD": {
      const list = [...state.basic_fields_schema];
      const [moved] = list.splice(action.fromIndex, 1);
      list.splice(action.toIndex, 0, moved);
      return { ...state, basic_fields_schema: list };
    }

    case "ADD_ENTRY": {
      const list = state[action.section] as ProfileEntry[];
      return {
        ...state,
        [action.section]: [...list, action.entry],
      };
    }

    case "SET_ENTRY_FIELD": {
      const list = state[action.section] as ProfileEntry[];
      return {
        ...state,
        [action.section]: list.map((e) =>
          e.id === action.entryId
            ? { ...e, [action.key]: action.value }
            : e
        ),
      };
    }

    case "DELETE_ENTRY": {
      const list = state[action.section] as ProfileEntry[];
      return {
        ...state,
        [action.section]: list.filter((e) => e.id !== action.entryId),
      };
    }

    case "SET_SELF_EVAL":
      return { ...state, self_evaluation: action.value };

    case "TOGGLE_MASKED_FIELD": {
      const present = state.masked_basic_fields.includes(action.key);
      const masked =
        action.checked === present
          ? state.masked_basic_fields
          : action.checked
            ? [...state.masked_basic_fields, action.key]
            : state.masked_basic_fields.filter((k) => k !== action.key);
      return { ...state, masked_basic_fields: masked };
    }

    default:
      return state;
  }
}

const ProfileStateContext = createContext<PersonalProfile | null>(null);
const ProfileDispatchContext = createContext<Dispatch<ProfileAction> | null>(
  null
);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(profileReducer, undefined, emptyProfile);
  return (
    <ProfileStateContext.Provider value={state}>
      <ProfileDispatchContext.Provider value={dispatch}>
        {children}
      </ProfileDispatchContext.Provider>
    </ProfileStateContext.Provider>
  );
}

export function useProfileState(): PersonalProfile {
  const ctx = useContext(ProfileStateContext);
  if (!ctx) throw new Error("useProfileState 必须在 ProfileProvider 内使用");
  return ctx;
}

export function useProfileDispatch(): Dispatch<ProfileAction> {
  const ctx = useContext(ProfileDispatchContext);
  if (!ctx) throw new Error("useProfileDispatch 必须在 ProfileProvider 内使用");
  return ctx;
}
