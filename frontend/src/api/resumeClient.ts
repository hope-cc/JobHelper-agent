import type { Resume, ResumeSummary } from "../types";

const BASE = "/api";

export async function listResumes(): Promise<ResumeSummary[]> {
  const res = await fetch(`${BASE}/resumes`);
  if (!res.ok) throw new Error(`获取简历列表失败: ${res.status}`);
  return res.json();
}

export async function createResume(): Promise<Resume> {
  const res = await fetch(`${BASE}/resumes`, { method: "POST" });
  if (!res.ok) throw new Error(`创建简历失败: ${res.status}`);
  return res.json();
}

export async function getResume(id: string): Promise<Resume> {
  const res = await fetch(`${BASE}/resumes/${id}`);
  if (!res.ok) throw new Error(`获取简历失败: ${res.status}`);
  return res.json();
}

export async function updateResume(id: string, data: Resume): Promise<void> {
  const res = await fetch(`${BASE}/resumes/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`更新简历失败: ${res.status}`);
}

export async function deleteResume(id: string): Promise<void> {
  const res = await fetch(`${BASE}/resumes/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`删除简历失败: ${res.status}`);
}

export async function copyResume(id: string): Promise<Resume> {
  const res = await fetch(`${BASE}/resumes/${id}/copy`, { method: "POST" });
  if (!res.ok) throw new Error(`复制简历失败: ${res.status}`);
  return res.json();
}

export async function uploadPhoto(
  id: string,
  file: File
): Promise<{ photoUrl: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE}/resumes/${id}/photo`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "上传失败" }));
    throw new Error(err.detail || `照片上传失败: ${res.status}`);
  }
  return res.json();
}

export function getPhotoUrl(id: string): string {
  return `${BASE}/resumes/${id}/photo`;
}

export async function generateResume(
  id: string
): Promise<{ success: boolean; pdf_url?: string; detail?: string }> {
  const res = await fetch(`${BASE}/resumes/${id}/generate`, { method: "POST" });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `生成失败: ${res.status}`);
  }
  return data;
}

export function getPdfUrl(id: string): string {
  return `${BASE}/resumes/${id}/preview`;
}

export function getDownloadUrl(id: string): string {
  return `${BASE}/resumes/${id}/download`;
}
