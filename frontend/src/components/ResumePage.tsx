import { useEffect } from "react";
import { ResumeProvider, useResumeState, useResumeDispatch } from "./ResumeContext";
import * as api from "../api/resumeClient";
import ResumeTopBar from "./ResumeTopBar";
import ResumeEditor from "./ResumeEditor";

function ResumePageInner() {
  const { resumes } = useResumeState();
  const dispatch = useResumeDispatch();

  useEffect(() => {
    api
      .listResumes()
      .then((list) => dispatch({ type: "LOAD_RESUMES", resumes: list }))
      .catch((err) => console.error("加载简历列表失败:", err));
  }, [dispatch]);

  return (
    <div className="h-full flex flex-col">
      <ResumeTopBar />
      <ResumeEditor />
    </div>
  );
}

export default function ResumePage() {
  return (
    <ResumeProvider>
      <ResumePageInner />
    </ResumeProvider>
  );
}
