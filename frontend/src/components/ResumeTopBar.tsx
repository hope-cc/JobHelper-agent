import { useResumeState, useResumeDispatch } from "./ResumeContext";
import * as api from "../api/resumeClient";
import ResumeCard from "./ResumeCard";

export default function ResumeTopBar() {
  const { resumes, currentResume } = useResumeState();
  const dispatch = useResumeDispatch();

  async function handleCreate() {
    try {
      const newResume = await api.createResume();
      const list = await api.listResumes();
      dispatch({ type: "LOAD_RESUMES", resumes: list });
      dispatch({ type: "SET_CURRENT_RESUME", resume: newResume });
    } catch (err) {
      console.error("创建简历失败:", err);
      alert("创建失败");
    }
  }

  async function handleSelect(resumeId: string) {
    if (currentResume?.id === resumeId) return;
    try {
      const full = await api.getResume(resumeId);
      dispatch({ type: "SET_CURRENT_RESUME", resume: full });
    } catch (err) {
      console.error("加载简历失败:", err);
    }
  }

  return (
    <div className="h-1/4 min-h-[160px] border-b border-gray-200 bg-gray-50 px-4 py-3">
      <h2 className="text-sm font-semibold text-gray-600 mb-2">我的简历</h2>
      <div className="flex gap-3 overflow-x-auto pb-2 items-stretch">
        {resumes.map((r) => (
          <ResumeCard
            key={r.id}
            resume={r}
            isActive={currentResume?.id === r.id}
            onEdit={() => handleSelect(r.id)}
          />
        ))}
        {/* 新建卡片 */}
        <button
          className="flex-shrink-0 w-[180px] h-[120px] rounded-xl border-2 border-dashed border-gray-300 bg-white hover:border-blue-400 hover:bg-blue-50/50 transition flex flex-col items-center justify-center gap-1 text-gray-400 hover:text-blue-500 cursor-pointer"
          onClick={handleCreate}
        >
          <span className="text-3xl font-light">+</span>
          <span className="text-xs">新建简历</span>
        </button>
      </div>
    </div>
  );
}
