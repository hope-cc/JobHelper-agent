import type { JobPayload, JobRecord } from "../types";

const BASE = "/api";

export async function listJobs(): Promise<JobRecord[]> {
  const res = await fetch(`${BASE}/jobs`);
  if (!res.ok) throw new Error(`获取投递记录失败: ${res.status}`);
  const data = await res.json();
  return data.jobs as JobRecord[];
}

export async function createJob(payload: JobPayload): Promise<JobRecord> {
  const res = await fetch(`${BASE}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`新增投递记录失败: ${res.status}`);
  return res.json();
}

export async function updateJob(
  id: string,
  payload: JobPayload
): Promise<JobRecord> {
  const res = await fetch(`${BASE}/jobs/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`更新投递记录失败: ${res.status}`);
  return res.json();
}