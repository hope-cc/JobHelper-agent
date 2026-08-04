import type { Conversation, ConversationSummary } from "../types";

const BASE = "/api";

export async function listConversations(): Promise<ConversationSummary[]> {
  const res = await fetch(`${BASE}/conversations`);
  if (!res.ok) throw new Error(`获取会话列表失败: ${res.status}`);
  return res.json();
}

export async function getConversation(id: string): Promise<Conversation> {
  const res = await fetch(`${BASE}/conversations/${id}`);
  if (!res.ok) throw new Error(`获取会话失败: ${res.status}`);
  return res.json();
}

export async function createConversation(): Promise<Conversation> {
  const res = await fetch(`${BASE}/conversations`, { method: "POST" });
  if (!res.ok) throw new Error(`创建会话失败: ${res.status}`);
  return res.json();
}

/**
 * 发送消息并返回 SSE 流的 reader。
 * 调用方通过 reader 逐行读取 SSE 事件。
 */
export async function sendMessage(
  id: string,
  content: string
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const res = await fetch(`${BASE}/conversations/${id}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error(`发送消息失败: ${res.status}`);
  if (!res.body) throw new Error("响应无 body");
  return res.body.getReader();
}
