import { useCallback, useEffect, useMemo, useState } from "react";
import * as jobClient from "../../api/jobClient";
import type { JobPayload, JobRecord, JobStatus } from "../../types";
import MetricCards from "./MetricCards";
import JobToolbar from "./JobToolbar";
import JobTable from "./JobTable";
import JobFormModal from "./JobFormModal";

const CSV_HEADER = ["时间", "公司", "岗位", "进度", "下一步", "备注"];

function todayMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function JobProgressPage() {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<JobStatus | "">("");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [modal, setModal] = useState<{
    mode: "create" | "edit";
    initial: JobRecord | null;
  } | null>(null);
  const [loadError, setLoadError] = useState("");

  // 加载全量记录
  useEffect(() => {
    jobClient
      .listJobs()
      .then(setJobs)
      .catch((err) => setLoadError(err.message));
  }, []);

  // 派生显示列表：搜索 + 进度筛选 + 时间排序
  const displayed = useMemo(() => {
    const kw = search.trim().toLowerCase();
    const list = jobs.filter((rec) => {
      if (kw) {
        const hit =
          rec.company.toLowerCase().includes(kw) ||
          rec.position.toLowerCase().includes(kw) ||
          rec.remark.toLowerCase().includes(kw);
        if (!hit) return false;
      }
      if (filter && rec.status !== filter) return false;
      return true;
    });
    return [...list].sort((a, b) => {
      const cmp = a.applied_at.localeCompare(b.applied_at);
      if (cmp !== 0) return sortDir === "desc" ? -cmp : cmp;
      // 同分时按 id 稳定排序（desc 下同样反转）
      const idCmp = a.id.localeCompare(b.id);
      return sortDir === "desc" ? -idCmp : idCmp;
    });
  }, [jobs, search, filter, sortDir]);

  // 派生统计数字（基于全量）
  const counts = useMemo(() => {
    const month = todayMonth();
    let active = 0;
    let offer = 0;
    let rejected = 0;
    let monthly = 0;
    for (const rec of jobs) {
      if (rec.status === "简历已投递" || rec.status === "评估中") active++;
      else if (rec.status === "Offer") offer++;
      else if (rec.status === "已拒绝") rejected++;
      if (rec.applied_at.startsWith(month)) monthly++;
    }
    return { total: jobs.length, active, offer, rejected, monthly };
  }, [jobs]);

  const handleCreate = useCallback(
    (payload: JobPayload) => {
      jobClient
        .createJob(payload)
        .then((rec) => {
          setJobs((prev) => [...prev, rec]);
          setModal(null);
        })
        .catch((err) => alert(err.message));
    },
    []
  );

  const handleUpdate = useCallback(
    (payload: JobPayload) => {
      if (!modal?.initial) return;
      jobClient
        .updateJob(modal.initial.id, payload)
        .then((rec) => {
          setJobs((prev) =>
            prev.map((r) => (r.id === rec.id ? rec : r))
          );
          setModal(null);
        })
        .catch((err) => alert(err.message));
    },
    [modal]
  );

  const handleExport = useCallback(() => {
    if (displayed.length === 0) {
      alert("当前没有可导出的记录");
      return;
    }
    const rows = displayed.map((rec) => [
      rec.applied_at,
      rec.company,
      rec.position,
      rec.status,
      rec.next_step,
      rec.remark,
    ]);
    const csv = [CSV_HEADER, ...rows]
      .map((row) =>
        row
          .map((cell) => `"${String(cell).replace(/"/g, '""')}"`)
          .join(",")
      )
      .join("\n");
    // UTF-8 BOM，便于 Excel 打开中文不乱码
    const blob = new Blob(["﻿" + csv], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "投递记录.csv";
    a.click();
    URL.revokeObjectURL(url);
  }, [displayed]);

  return (
    <div className="h-full overflow-y-auto bg-slate-100">
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        {/* A. 顶部 Header */}
        <header className="flex items-start justify-between">
          <div>
            <div className="text-blue-600 text-sm font-bold">秋招投递记录</div>
            <h1 className="text-2xl font-bold text-slate-900 mt-1">
              秋招投递进度
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              记录投递、测评和反馈，随时掌握求职节奏
            </p>
          </div>
          <button
            onClick={() => setModal({ mode: "create", initial: null })}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm"
          >
            + 新增记录
          </button>
        </header>

        {loadError && (
          <div className="bg-rose-50 text-rose-700 border border-rose-200 rounded-xl px-4 py-3 text-sm">
            加载失败：{loadError}
          </div>
        )}

        {/* B. 统计卡片栏 */}
        <MetricCards
          total={counts.total}
          active={counts.active}
          offer={counts.offer}
          rejected={counts.rejected}
          monthly={counts.monthly}
        />

        {/* C. 数据管理主卡片 */}
        <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="text-lg font-semibold text-slate-900">投递记录</h2>
            <span className="text-xs text-slate-400">共 {displayed.length} 条</span>
          </div>

          <JobToolbar
            search={search}
            filter={filter}
            sortDir={sortDir}
            onSearchChange={setSearch}
            onFilterChange={setFilter}
            onSortChange={setSortDir}
            onExport={handleExport}
          />

          <div className="mt-4 overflow-x-auto">
            <JobTable records={displayed} onEdit={(rec) => setModal({ mode: "edit", initial: rec })} />
          </div>
        </section>
      </div>

      {modal && (
        <JobFormModal
          mode={modal.mode}
          initial={modal.initial}
          onClose={() => setModal(null)}
          onSubmit={modal.mode === "create" ? handleCreate : handleUpdate}
        />
      )}
    </div>
  );
}