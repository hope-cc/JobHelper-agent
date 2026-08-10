import { useState, useRef, useEffect, useCallback } from "react";
import { useResumeState, useResumeDispatch } from "./ResumeContext";
import * as api from "../api/resumeClient";
import type { Block } from "../types";

let blockIdCounter = 0;
function newBlockId(): string {
  blockIdCounter++;
  return `block-${Date.now()}-${blockIdCounter}`;
}

export default function EditorToolbar() {
  const { currentResume, selectedBlockId } = useResumeState();
  const dispatch = useResumeDispatch();
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
      setAddMenuOpen(false);
    }
  }, []);

  useEffect(() => {
    if (addMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [addMenuOpen, handleClickOutside]);

  function handleAddBlock(type: "personal_info" | "content") {
    setAddMenuOpen(false);
    const yOffset = (currentResume?.blocks.length ?? 0) * 220 + 20;
    const block: Block = {
      id: newBlockId(),
      type,
      position: { x: 100, y: yOffset },
    };
    if (type === "personal_info") {
      block.personalInfo = {
        name: "",
        phone: "",
        email: "",
        location: "",
        photoUrl: null,
      };
    } else {
      block.content = {
        category: "项目经历",
        timeSpan: "",
        spans: [],
        bulletPoints: false,
      };
    }
    dispatch({ type: "ADD_BLOCK", block });
  }

  function handleDeleteBlock() {
    if (!selectedBlockId) return;
    dispatch({ type: "DELETE_BLOCK", blockId: selectedBlockId });
  }

  async function handleGenerate() {
    if (!currentResume) return;
    setGenerating(true);
    try {
      // 先保存
      await api.updateResume(currentResume.id, currentResume);
      // 再生成
      await api.generateResume(currentResume.id);
      alert("简历 PDF 生成成功！可点击预览查看");
    } catch (err: any) {
      console.error("生成失败:", err);
      alert("生成失败: " + (err.message || "未知错误"));
    } finally {
      setGenerating(false);
    }
  }

  function handlePreview() {
    if (!currentResume) return;
    window.open(api.getPdfUrl(currentResume.id), "_blank");
  }

  async function handleSave() {
    if (!currentResume) return;
    setSaving(true);
    try {
      await api.updateResume(currentResume.id, currentResume);
    } catch (err) {
      console.error("保存失败:", err);
      alert("保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-200 bg-white">
      {/* 新增文本块 + 下拉菜单 */}
      <div className="relative" ref={menuRef}>
        <button
          className="px-3 py-1.5 text-sm font-medium bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition"
          onClick={() => setAddMenuOpen(!addMenuOpen)}
        >
          + 新增文本块
        </button>
        {addMenuOpen && (
          <div className="absolute top-full left-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-20 min-w-[140px]">
            <button
              className="block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100"
              onClick={() => handleAddBlock("personal_info")}
            >
              👤 个人信息块
            </button>
            <button
              className="block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100"
              onClick={() => handleAddBlock("content")}
            >
              📝 正文内容块
            </button>
          </div>
        )}
      </div>

      {/* 删除文本块 */}
      <button
        className={`px-3 py-1.5 text-sm font-medium rounded-lg transition ${
          selectedBlockId
            ? "bg-red-500 text-white hover:bg-red-600"
            : "bg-gray-200 text-gray-400 cursor-not-allowed"
        }`}
        onClick={handleDeleteBlock}
        disabled={!selectedBlockId}
      >
        🗑 删除文本块
      </button>

      <div className="flex-1" />

      {/* 预览 */}
      <button
        className="px-3 py-1.5 text-sm font-medium border border-blue-400 text-blue-600 bg-white rounded-lg hover:bg-blue-50 transition"
        onClick={handlePreview}
      >
        👁 预览
      </button>

      {/* 生成简历 */}
      <button
        className="px-3 py-1.5 text-sm font-medium bg-green-500 text-white rounded-lg hover:bg-green-600 transition disabled:opacity-50"
        onClick={handleGenerate}
        disabled={generating}
      >
        {generating ? "生成中..." : "📄 生成简历"}
      </button>

      {/* 保存 */}
      <button
        className="px-3 py-1.5 text-sm font-medium bg-gray-700 text-white rounded-lg hover:bg-gray-800 transition disabled:opacity-50"
        onClick={handleSave}
        disabled={saving}
      >
        {saving ? "保存中..." : "💾 保存"}
      </button>
    </div>
  );
}
