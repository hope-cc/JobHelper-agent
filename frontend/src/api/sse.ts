/**
 * SSE 流解析工具。
 * 从 ReadableStream reader 中逐行读取 SSE 事件，
 * 每收到一个 text/done 事件时调用对应回调。
 */

export type SSECallbacks = {
  onText: (delta: string) => void;
  onDone: () => void;
  onError?: (error: Error) => void;
  onToolStart?: (toolId: string, toolName: string) => void;
  onToolDelta?: (toolId: string, delta: string) => void;
  onToolEnd?: (toolId: string) => void;
  onToolResult?: (toolId: string, content: string, isError: boolean) => void;
};

export async function parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  callbacks: SSECallbacks
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE 事件以 \n\n 分隔
      const parts = buffer.split("\n\n");
      // 最后一段可能不完整，保留到下次
      buffer = parts.pop() || "";

      for (const part of parts) {
        if (!part.trim()) continue;
        const lines = part.split("\n");
        let eventType = "";
        let dataStr = "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            dataStr = line.slice(6).trim();
          }
        }

        if (eventType === "text" && dataStr) {
          try {
            const parsed = JSON.parse(dataStr);
            callbacks.onText(parsed.delta || "");
          } catch {
            // 忽略解析失败的 data
          }
        } else if (eventType === "tool_start" && dataStr) {
          try {
            const parsed = JSON.parse(dataStr);
            callbacks.onToolStart?.(parsed.tool_id || "", parsed.tool_name || "");
          } catch {
            // 忽略
          }
        } else if (eventType === "tool_delta" && dataStr) {
          try {
            const parsed = JSON.parse(dataStr);
            callbacks.onToolDelta?.(parsed.tool_id || "", parsed.delta || "");
          } catch {
            // 忽略
          }
        } else if (eventType === "tool_end" && dataStr) {
          try {
            const parsed = JSON.parse(dataStr);
            callbacks.onToolEnd?.(parsed.tool_id || "");
          } catch {
            // 忽略
          }
        } else if (eventType === "tool_result" && dataStr) {
          try {
            const parsed = JSON.parse(dataStr);
            callbacks.onToolResult?.(parsed.tool_id || "", parsed.content || "", parsed.is_error || false);
          } catch {
            // 忽略
          }
        } else if (eventType === "error") {
          const message = (() => {
            try { return JSON.parse(dataStr).message || dataStr; } catch { return dataStr; }
          })();
          callbacks.onError?.(new Error(message));
          callbacks.onDone();
          return;
        } else if (eventType === "done") {
          callbacks.onDone();
          return;
        }
      }
    }
  } catch (err) {
    callbacks.onError?.(err instanceof Error ? err : new Error(String(err)));
  }
}
