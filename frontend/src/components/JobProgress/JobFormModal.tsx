import { useState } from "react";
import { JOB_STATUSES, type JobPayload, type JobRecord } from "../../types";

interface JobFormModalProps {
  mode: "create" | "edit";
  initial: JobRecord | null;
  onClose: () => void;
  onSubmit: (payload: JobPayload) => void;
}

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

export default function JobFormModal({
  mode,
  initial,
  onClose,
  onSubmit,
}: JobFormModalProps) {
  const [company, setCompany] = useState(initial?.company ?? "");
  const [position, setPosition] = useState(initial?.position ?? "");
  const [industry, setIndustry] = useState(initial?.industry ?? "");
  const [appliedAt, setAppliedAt] = useState(initial?.applied_at ?? today());
  const [status, setStatus] = useState(initial?.status ?? "简历已投递");
  const [nextStep, setNextStep] = useState(initial?.next_step ?? "");
  const [remark, setRemark] = useState(initial?.remark ?? "");
  const [error, setError] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!company.trim() || !position.trim()) {
      setError("公司和岗位不能为空");
      return;
    }
    onSubmit({
      company: company.trim(),
      position: position.trim(),
      industry: industry.trim(),
      applied_at: appliedAt,
      status,
      next_step: nextStep,
      remark,
    });
  }

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">
          {mode === "create" ? "新增投递记录" : "编辑投递记录"}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-1">
              <label className="block text-sm text-slate-600 mb-1">公司 *</label>
              <input
                type="text"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/30"
              />
            </div>
            <div className="col-span-1">
              <label className="block text-sm text-slate-600 mb-1">岗位 *</label>
              <input
                type="text"
                value={position}
                onChange={(e) => setPosition(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/30"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-slate-600 mb-1">行业</label>
            <input
              type="text"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/30"
              placeholder="如：互联网、新能源（选填）"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-1">
              <label className="block text-sm text-slate-600 mb-1">投递时间 *</label>
              <input
                type="date"
                value={appliedAt}
                onChange={(e) => setAppliedAt(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/30"
              />
            </div>
            <div className="col-span-1">
              <label className="block text-sm text-slate-600 mb-1">进度 *</label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as (typeof JOB_STATUSES)[number])}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/30"
              >
                {JOB_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm text-slate-600 mb-1">下一步</label>
            <input
              type="text"
              value={nextStep}
              onChange={(e) => setNextStep(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/30"
              placeholder="如：等待一面通知"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-600 mb-1">备注</label>
            <textarea
              value={remark}
              onChange={(e) => setRemark(e.target.value)}
              rows={2}
              className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/30 resize-none"
            />
          </div>

          {error && <p className="text-rose-600 text-sm">{error}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-100 text-slate-700 text-sm font-medium hover:bg-slate-200 transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
            >
              保存
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}