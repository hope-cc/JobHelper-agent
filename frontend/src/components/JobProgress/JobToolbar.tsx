import { useEffect, useState } from "react";
import { JOB_STATUSES, type JobStatus } from "../../types";

interface JobToolbarProps {
  search: string;
  filter: JobStatus | "";
  sortDir: "desc" | "asc";
  onSearchChange: (v: string) => void;
  onFilterChange: (v: JobStatus | "") => void;
  onSortChange: (v: "desc" | "asc") => void;
  onExport: () => void;
}

export default function JobToolbar({
  search,
  filter,
  sortDir,
  onSearchChange,
  onFilterChange,
  onSortChange,
  onExport,
}: JobToolbarProps) {
  const [input, setInput] = useState(search);

  // 搜索防抖 300ms
  useEffect(() => {
    const t = setTimeout(() => {
      if (input !== search) onSearchChange(input);
    }, 300);
    return () => clearTimeout(t);
  }, [input, search, onSearchChange]);

  return (
    <div className="flex items-center gap-3 flex-wrap">
      {/* 搜索输入框 */}
      <div className="relative w-[45%] min-w-[240px]">
        <svg
          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 21l-4.35-4.35M17 10.5a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0z"
          />
        </svg>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="搜索公司、岗位或备注..."
          className="w-full pl-10 pr-3 py-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-500"
        />
      </div>

      {/* 进度筛选 */}
      <select
        value={filter}
        onChange={(e) => onFilterChange(e.target.value as JobStatus | "")}
        className="px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
      >
        <option value="">全部进度 ▾</option>
        {JOB_STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>

      {/* 时间排序 */}
      <select
        value={sortDir}
        onChange={(e) => onSortChange(e.target.value as "desc" | "asc")}
        className="px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
      >
        <option value="desc">时间: 新到旧 ▾</option>
        <option value="asc">时间: 旧到新 ▾</option>
      </select>

      {/* 导出 */}
      <button
        onClick={onExport}
        className="ml-auto px-4 py-2 rounded-lg bg-slate-100 text-slate-700 text-sm font-medium hover:bg-slate-200 transition-colors"
      >
        导出 CSV
      </button>
    </div>
  );
}