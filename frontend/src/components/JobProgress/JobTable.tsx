import type { JobRecord, JobStatus } from "../../types";

/** 各状态的胶囊徽章配色（浅背景 + 深文字 + 浅边框） */
const JOB_STATUS_STYLE: Record<JobStatus, string> = {
  评估中: "bg-amber-50 text-amber-700 border-amber-200",
  简历已投递: "bg-sky-50 text-sky-700 border-sky-200",
  Offer: "bg-emerald-50 text-emerald-700 border-emerald-200",
  已拒绝: "bg-rose-50 text-rose-700 border-rose-200",
};

interface JobTableProps {
  records: JobRecord[];
  onEdit: (record: JobRecord) => void;
}

export default function JobTable({ records, onEdit }: JobTableProps) {
  if (records.length === 0) {
    return (
      <div className="text-slate-400 text-center py-16 text-sm">
        暂无投递记录，点击右上角新增
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="bg-slate-50 text-slate-500 text-left text-xs font-medium">
          <th className="px-4 py-3 rounded-l-lg font-medium">时间</th>
          <th className="px-4 py-3 font-medium">公司</th>
          <th className="px-4 py-3 font-medium">岗位</th>
          <th className="px-4 py-3 font-medium">行业</th>
          <th className="px-4 py-3 font-medium">进度</th>
          <th className="px-4 py-3 font-medium">下一步</th>
          <th className="px-4 py-3 rounded-r-lg font-medium">操作</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {records.map((rec) => (
          <tr
            key={rec.id}
            className="hover:bg-slate-50 transition-colors"
          >
            <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
              {rec.applied_at}
            </td>
            <td className="px-4 py-3 font-semibold text-slate-800">
              {rec.company}
            </td>
            <td className="px-4 py-3 text-slate-600">{rec.position}</td>
            <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
              {rec.industry || "—"}
            </td>
            <td className="px-4 py-3">
              <span
                className={`inline-block rounded-full px-3 py-1 text-xs font-medium border ${JOB_STATUS_STYLE[rec.status]}`}
              >
                {rec.status}
              </span>
            </td>
            <td className="px-4 py-3 text-slate-600">{rec.next_step}</td>
            <td className="px-4 py-3">
              <button
                onClick={() => onEdit(rec)}
                className="text-blue-600 hover:underline text-sm"
              >
                编辑
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}