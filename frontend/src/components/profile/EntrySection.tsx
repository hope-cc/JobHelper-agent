import { useState } from "react";
import type { ProfileEntry, ProfileSectionKey } from "../../types";
import type { ProfileFieldConfig } from "./profileFieldConfigs";
import { createEmptyEntry } from "./profileFieldConfigs";
import { useProfileDispatch, useProfileState } from "../ProfileContext";
import SectionCard from "./SectionCard";

const INPUT_CLASS =
  "w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

interface EntrySectionProps {
  title: string;
  section: ProfileSectionKey;
  fields: ProfileFieldConfig[];
}

/**
 * 通用条目分区：教育/实习/项目/奖项/语言共用。
 * 支持添加、展开编辑、删除；字段渲染由传入的 fields 配置驱动。
 */
export default function EntrySection({
  title,
  section,
  fields,
}: EntrySectionProps) {
  const state = useProfileState();
  const dispatch = useProfileDispatch();
  const [editingId, setEditingId] = useState<string | null>(null);

  const entries = state[section] as ProfileEntry[];

  function handleAdd() {
    const entry = createEmptyEntry(section, fields);
    dispatch({ type: "ADD_ENTRY", section, entry });
    setEditingId(entry.id);
  }

  function handleDelete(entryId: string) {
    dispatch({ type: "DELETE_ENTRY", section, entryId });
    if (editingId === entryId) setEditingId(null);
  }

  function handleFieldChange(entryId: string, key: string, value: string) {
    dispatch({ type: "SET_ENTRY_FIELD", section, entryId, key, value });
  }

  function renderField(entry: Record<string, string>, field: ProfileFieldConfig) {
    return (
      <label
        key={field.key}
        className={`block ${field.span ? "md:col-span-2" : ""}`}
      >
        <span className="block text-sm text-gray-600 mb-1">{field.label}</span>
        {field.type === "textarea" ? (
          <textarea
            rows={3}
            value={entry[field.key] ?? ""}
            onChange={(e) =>
              handleFieldChange(entry.id, field.key, e.target.value)
            }
            className={INPUT_CLASS}
          />
        ) : field.type === "select" ? (
          <select
            value={entry[field.key] ?? ""}
            onChange={(e) =>
              handleFieldChange(entry.id, field.key, e.target.value)
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
            value={entry[field.key] ?? ""}
            onChange={(e) =>
              handleFieldChange(entry.id, field.key, e.target.value)
            }
            className={INPUT_CLASS}
          />
        )}
      </label>
    );
  }

  function summaryText(entry: Record<string, string>): string {
    const parts = fields
      .map((f) => (entry[f.key] ?? "").trim())
      .filter(Boolean);
    return parts.length > 0 ? parts.join(" · ") : "（空）";
  }

  return (
    <SectionCard title={title} onAdd={handleAdd}>
      {entries.length === 0 && editingId === null && (
        <p className="text-sm text-gray-400">暂无记录，点击右上角「+ 添加」</p>
      )}
      <ul className="space-y-3">
        {entries.map((entry) => {
          const rec = entry as unknown as Record<string, string>;
          const isEditing = editingId === entry.id;
          return (
            <li key={entry.id} className="border border-gray-200 rounded-md p-3">
              {isEditing ? (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {fields.map((f) => renderField(rec, f))}
                  </div>
                  <div className="mt-3 flex justify-end">
                    <button
                      type="button"
                      onClick={() => setEditingId(null)}
                      className="text-xs text-gray-500 hover:text-gray-700"
                    >
                      完成
                    </button>
                  </div>
                </>
              ) : (
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm text-gray-700 flex-1">
                    {summaryText(rec)}
                  </p>
                  <div className="flex gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => setEditingId(entry.id)}
                      className="text-xs text-blue-600 hover:text-blue-800"
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(entry.id)}
                      className="text-xs text-red-500 hover:text-red-700"
                    >
                      删除
                    </button>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </SectionCard>
  );
}
