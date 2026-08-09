import { useState } from "react";
import type { ToolCallState } from "../types";

interface ToolCallCardProps {
  toolCall: ToolCallState;
}

export default function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);

  const { toolName, argsJson, result, status } = toolCall;

  // 尝试格式化 JSON 参数用于展示
  let argsDisplay = argsJson;
  try {
    if (argsJson) {
      argsDisplay = JSON.stringify(JSON.parse(argsJson), null, 2);
    }
  } catch {
    argsDisplay = argsJson;
  }

  // 结果截断为一行摘要
  const resultSummary = result
    ? result.length > 100
      ? result.slice(0, 100) + "..."
      : result
    : null;

  return (
    <div className="mt-2 rounded-lg border border-gray-200 bg-white text-sm">
      {/* 折叠标题栏 */}
      <button
        className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-gray-50 rounded-lg"
        onClick={() => setExpanded(!expanded)}
      >
        {/* 状态图标 */}
        <span className="flex-shrink-0">
          {status === "running" && (
            <span className="inline-block w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
          )}
          {status === "done" && (
            <span className="inline-block text-green-500">&#10003;</span>
          )}
          {status === "error" && (
            <span className="inline-block text-red-500">&#10007;</span>
          )}
        </span>

        {/* 工具名 */}
        <span className="font-medium text-gray-700">{toolName}</span>

        {/* 结果摘要（折叠时可见） */}
        {!expanded && resultSummary && (
          <span className="text-gray-400 truncate flex-1 min-w-0">
            &mdash; {resultSummary}
          </span>
        )}

        {/* 展开/收起箭头 */}
        <span className="ml-auto text-gray-400 text-xs">
          {expanded ? "收起" : "展开"}
        </span>
      </button>

      {/* 展开内容 */}
      {expanded && (
        <div className="px-3 pb-3 pt-1 space-y-2">
          {/* 参数 */}
          {argsDisplay && (
            <div>
              <div className="text-xs text-gray-400 mb-1">参数</div>
              <pre className="text-xs bg-gray-50 rounded p-2 overflow-x-auto whitespace-pre-wrap text-gray-600">
                {argsDisplay}
              </pre>
            </div>
          )}

          {/* 结果 */}
          {result !== null && (
            <div>
              <div className="text-xs text-gray-400 mb-1">
                {status === "error" ? "错误" : "结果"}
              </div>
              <pre
                className={`text-xs rounded p-2 overflow-x-auto whitespace-pre-wrap ${
                  status === "error"
                    ? "bg-red-50 text-red-600"
                    : "bg-gray-50 text-gray-600"
                }`}
              >
                {result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
