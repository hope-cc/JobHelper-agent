import type { SavableProfile } from "../types";

const BASE = "/api";

export async function getPersonal(): Promise<SavableProfile> {
  const res = await fetch(`${BASE}/personal`);
  if (!res.ok) throw new Error(`获取个人信息失败: ${res.status}`);
  return res.json();
}

export async function savePersonal(data: SavableProfile): Promise<void> {
  const res = await fetch(`${BASE}/personal`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`保存个人信息失败: ${res.status}`);
}
