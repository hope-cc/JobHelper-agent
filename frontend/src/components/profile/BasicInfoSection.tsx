import type { BasicInfo } from "../../types";
import SectionCard from "./SectionCard";
import { BASIC_INFO_FIELDS } from "./profileFieldConfigs";
import { useProfileState, useProfileDispatch } from "../ProfileContext";

const INPUT_CLASS =
  "w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

export default function BasicInfoSection() {
  const { basic_info, masked_basic_fields } = useProfileState();
  const dispatch = useProfileDispatch();

  return (
    <SectionCard title="基本信息">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {BASIC_INFO_FIELDS.map((field) => (
        <div key={field.key} className="block">
          <span className="flex items-center justify-between mb-1">
            <span className="block text-sm text-gray-600">{field.label}</span>
            <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={masked_basic_fields.includes(field.key)}
                onChange={(e) =>
                  dispatch({
                    type: "TOGGLE_MASKED_FIELD",
                    key: field.key,
                    checked: e.target.checked,
                  })
                }
                className="h-3.5 w-3.5"
              />
              脱敏
            </label>
          </span>
          {field.type === "select" ? (
            <select
              value={basic_info[field.key as keyof BasicInfo]}
              onChange={(e) =>
                dispatch({
                  type: "SET_BASIC_FIELD",
                  key: field.key,
                  value: e.target.value,
                })
              }
              className={INPUT_CLASS}
            >
              <option value="">请选择</option>
              {field.options?.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={basic_info[field.key as keyof BasicInfo]}
              onChange={(e) =>
                dispatch({
                  type: "SET_BASIC_FIELD",
                  key: field.key,
                  value: e.target.value,
                })
              }
              className={INPUT_CLASS}
            />
          )}
        </div>
      ))}
      </div>
    </SectionCard>
  );
}
