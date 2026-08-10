import { useState, useRef, useEffect, useCallback } from "react";
import { useResumeDispatch } from "./ResumeContext";
import * as api from "../api/resumeClient";
import type { ResumeSummary } from "../types";

interface ResumeCardProps {
  resume: ResumeSummary;
  isActive: boolean;
  onEdit: () => void;
}

function formatRelativeTime(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour} 小时前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return `${diffDay} 天前`;
  const diffMonth = Math.floor(diffDay / 30);
  if (diffMonth < 12) return `${diffMonth} 个月前`;
  return `${Math.floor(diffMonth / 12)} 年前`;
}

export default function ResumeCard({ resume, isActive, onEdit }: ResumeCardProps) {
  const dispatch = useResumeDispatch();
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(resume.name);
  const menuRef = useRef<HTMLDivElement>(null);

  // 关闭菜单的点击外部处理
  const handleClickOutside = useCallback(
    (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    },
    []
  );

  useEffect(() => {
    if (menuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen, handleClickOutside]);

  function handleDoubleClick() {
    setEditing(true);
    setName(resume.name);
  }

  function handleNameConfirm() {
    setEditing(false);
    if (name.trim() && name !== resume.name) {
      dispatch({ type: "UPDATE_RESUME_NAME", name: name.trim() });
    }
  }

  async function handleCopy() {
    setMenuOpen(false);
    try {
      const newResume = await api.copyResume(resume.id);
      // 重新加载列表以保证数据一致
      const list = await api.listResumes();
      dispatch({ type: "LOAD_RESUMES", resumes: list });
      dispatch({ type: "SET_CURRENT_RESUME", resume: newResume });
    } catch (err) {
      console.error("复制简历失败:", err);
      alert("复制失败");
    }
  }

  async function handleDelete() {
    setMenuOpen(false);
    if (!confirm(`确定要删除简历「${resume.name}」吗？此操作不可恢复。`)) return;
    try {
      await api.deleteResume(resume.id);
      dispatch({ type: "REMOVE_RESUME", resumeId: resume.id });
    } catch (err) {
      console.error("删除简历失败:", err);
      alert("删除失败");
    }
  }

  function handleDownload() {
    setMenuOpen(false);
    const url = api.getDownloadUrl(resume.id);
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  return (
    <div
      className={`relative flex-shrink-0 w-[180px] h-[120px] rounded-xl border-2 p-3 cursor-pointer transition flex flex-col justify-between ${
        isActive
          ? "border-blue-500 bg-blue-50"
          : "border-gray-200 bg-white hover:border-gray-300"
      }`}
      onClick={onEdit}
    >
      {/* 三点菜单按钮 */}
      <div className="absolute top-1 right-1" ref={menuRef}>
        <button
          className="w-6 h-6 flex items-center justify-center rounded-full text-gray-500 hover:bg-gray-200 text-lg leading-none"
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen(!menuOpen);
          }}
        >
          ⋮
        </button>
        {menuOpen && (
          <div className="absolute top-7 right-0 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-20 min-w-[100px]">
            <button
              className="block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen(false);
                onEdit();
              }}
            >
              ✏️ 编辑
            </button>
            <button
              className="block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100"
              onClick={(e) => {
                e.stopPropagation();
                handleDownload();
              }}
            >
              ⬇️ 下载
            </button>
            <button
              className="block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100"
              onClick={(e) => {
                e.stopPropagation();
                handleCopy();
              }}
            >
              📋 复制
            </button>
            <button
              className="block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 text-red-500"
              onClick={(e) => {
                e.stopPropagation();
                handleDelete();
              }}
            >
              🗑️ 删除
            </button>
          </div>
        )}
      </div>

      {/* 简历名称 */}
      <div className="flex-1 flex items-center">
        {editing ? (
          <input
            className="w-full text-sm font-medium border border-blue-400 rounded px-1 py-0.5 outline-none"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={handleNameConfirm}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleNameConfirm();
              if (e.key === "Escape") setEditing(false);
            }}
            onClick={(e) => e.stopPropagation()}
            autoFocus
          />
        ) : (
          <span
            className="text-sm font-medium text-gray-800 line-clamp-2"
            onDoubleClick={(e) => {
              e.stopPropagation();
              handleDoubleClick();
            }}
          >
            {resume.name}
          </span>
        )}
      </div>

      {/* 更新时间 */}
      <p className="text-xs text-gray-400 mt-1">
        {formatRelativeTime(resume.updated_at)}
      </p>
    </div>
  );
}
