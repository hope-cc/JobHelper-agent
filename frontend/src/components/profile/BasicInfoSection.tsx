import { useState, type ChangeEvent } from "react";
import type { BasicFieldSchema } from "../../types";
import SectionCard from "./SectionCard";
import { sanitizeFieldKey } from "./profileFieldConfigs";
import { useProfileState, useProfileDispatch } from "../ProfileContext";

const INPUT_CLASS =
  "w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

type FieldType = BasicFieldSchema["type"];

/**
 * 基本信息区：字段由持久化的 basic_fields_schema 驱动渲染（而非代码写死）。
 * 支持：改名、删除、拖拽排序、新增自定义字段；每个字段保留脱敏勾选。
 */
export default function BasicInfoSection() {
  const { basic_fields_schema, basic_info, masked_basic_fields } =
    useProfileState();
  const dispatch = useProfileDispatch();

  // 新增字段表单状态
  const [adding, setAdding] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [newType, setNewType] = useState<FieldType>("text");
  const [newOptions, setNewOptions] = useState("");

  // 改名状态
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState("");

  // 拖拽状态
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  function handleAddField() {
    const label = newLabel.trim();
    if (!label) return;
    const key = sanitizeFieldKey(
      label,
      basic_fields_schema.map((f) => f.key)
    );
    const schema: BasicFieldSchema = { key, label, type: newType };
    if (newType === "select") {
      const opts = newOptions
        .split(/[,，]/)
        .map((s) => s.trim())
        .filter(Boolean);
      if (opts.length > 0) schema.options = opts;
    }
    dispatch({ type: "ADD_BASIC_FIELD", schema });
    setNewLabel("");
    setNewOptions("");
    setNewType("text");
    setAdding(false);
  }

  function commitRename() {
    const label = editLabel.trim();
    if (editingKey && label) {
      dispatch({ type: "RENAME_BASIC_FIELD", key: editingKey, label });
    }
    setEditingKey(null);
  }

  function renderInput(field: BasicFieldSchema) {
    const value = basic_info[field.key] ?? "";
    const onChange = (
      e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
    ) =>
      dispatch({ type: "SET_BASIC_FIELD", key: field.key, value: e.target.value });

    if (field.type === "textarea") {
      return (
        <textarea
          rows={2}
          value={value}
          onChange={onChange}
          className={INPUT_CLASS}
        />
      );
    }
    if (field.type === "select") {
      return (
        <select value={value} onChange={onChange} className={INPUT_CLASS}>
          <option value="">请选择</option>
          {field.options?.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      );
    }
    return (
      <input type="text" value={value} onChange={onChange} className={INPUT_CLASS} />
    );
  }

  function handleDrop(index: number) {
    if (dragIndex !== null && dragIndex !== index) {
      dispatch({ type: "MOVE_BASIC_FIELD", fromIndex: dragIndex, toIndex: index });
    }
    setDragIndex(null);
  }

  return (
    <SectionCard title="基本信息">
      <div className="space-y-3">
        {basic_fields_schema.length === 0 && (
          <p className="text-sm text-gray-400">暂无字段，点击下方「添加字段」</p>
        )}

        {basic_fields_schema.map((field, index) => (
          <div
            key={field.key}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => handleDrop(index)}
            className="flex items-center gap-3 border border-gray-200 rounded-md p-3"
          >
            <span
              draggable
              onDragStart={() => setDragIndex(index)}
              className="text-gray-400 cursor-grab select-none"
              title="拖动排序"
            >
              ⠿
            </span>

            <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-3 items-center">
              {editingKey === field.key ? (
                <input
                  type="text"
                  value={editLabel}
                  autoFocus
                  onChange={(e) => setEditLabel(e.target.value)}
                  onBlur={commitRename}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename();
                  }}
                  className={INPUT_CLASS}
                />
              ) : (
                <span className="text-sm text-gray-600">{field.label}</span>
              )}
              {renderInput(field)}
            </div>

            <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none shrink-0">
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

            <div className="flex gap-2 shrink-0">
              <button
                type="button"
                onClick={() => {
                  setEditingKey(field.key);
                  setEditLabel(field.label);
                }}
                className="text-xs text-blue-600 hover:text-blue-800"
                title="改名"
              >
                改
              </button>
              <button
                type="button"
                onClick={() =>
                  dispatch({ type: "DELETE_BASIC_FIELD", key: field.key })
                }
                className="text-xs text-red-500 hover:text-red-700"
                title="删除"
              >
                删
              </button>
            </div>
          </div>
        ))}

        {adding ? (
          <div className="border border-blue-200 rounded-md p-3 space-y-2 bg-blue-50/40">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <input
                type="text"
                placeholder="字段标签（如 微信号）"
                value={newLabel}
                autoFocus
                onChange={(e) => setNewLabel(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleAddField();
                }}
                className={INPUT_CLASS}
              />
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value as FieldType)}
                className={INPUT_CLASS}
              >
                <option value="text">单行文本</option>
                <option value="textarea">多行文本</option>
                <option value="select">下拉选择</option>
              </select>
              {newType === "select" && (
                <input
                  type="text"
                  placeholder="选项（逗号分隔）"
                  value={newOptions}
                  onChange={(e) => setNewOptions(e.target.value)}
                  className={INPUT_CLASS}
                />
              )}
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setAdding(false);
                  setNewLabel("");
                  setNewOptions("");
                }}
                className="text-xs text-gray-500 hover:text-gray-700"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleAddField}
                disabled={!newLabel.trim()}
                className="px-3 py-1 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-md"
              >
                确定
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="w-full py-2 text-sm text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-md transition"
          >
            + 添加字段
          </button>
        )}
      </div>
    </SectionCard>
  );
}
