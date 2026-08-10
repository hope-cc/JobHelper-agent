import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Block } from "../types";

export type BlockNodeData = {
  block: Block;
  isSelected: boolean;
  onEdit: () => void;
};

function spansToHtml(spans: { text: string; bold: boolean }[] | undefined): string {
  if (!spans || spans.length === 0) return "";
  return spans
    .map((s) =>
      s.bold ? `<b>${s.text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</b>` : s.text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    )
    .join("");
}

function BlockNodeComponent({ data, selected }: NodeProps) {
  const { block, isSelected, onEdit } = data as unknown as BlockNodeData;
  const isSelectedFinal = selected || isSelected;

  return (
    <div
      className={`relative min-w-[200px] max-w-[260px] rounded-xl border-2 p-3 bg-white shadow-sm transition ${
        isSelectedFinal ? "border-blue-500" : "border-gray-200"
      }`}
    >
      {/* 左输入端口 */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-3 !h-3 !bg-gray-400 !border-2 !border-white hover:!bg-blue-500"
      />

      {/* 右输出端口 */}
      <Handle
        type="source"
        position={Position.Right}
        className="!w-3 !h-3 !bg-gray-400 !border-2 !border-white hover:!bg-blue-500"
      />

      {/* 类型标签 + 编辑按钮 */}
      <div className="flex items-center justify-between mb-2">
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
            block.type === "personal_info"
              ? "bg-purple-100 text-purple-700"
              : "bg-green-100 text-green-700"
          }`}
        >
          {block.type === "personal_info" ? "个人信息" : "正文"}
        </span>
        <button
          className="w-6 h-6 flex items-center justify-center rounded-full text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition text-xs"
          title="编辑"
          onClick={(e) => {
            e.stopPropagation();
            onEdit();
          }}
        >
          ✏️
        </button>
      </div>

      {/* 内容摘要 */}
      {block.type === "personal_info" ? (
        <div className="text-sm text-gray-700 space-y-0.5">
          {block.personalInfo?.name ? (
            <>
              <p className="font-medium">{block.personalInfo.name}</p>
              {block.personalInfo.phone && (
                <p className="text-xs text-gray-500">{block.personalInfo.phone}</p>
              )}
              {block.personalInfo.email && (
                <p className="text-xs text-gray-500">{block.personalInfo.email}</p>
              )}
              {block.personalInfo.photoUrl && (
                <img
                  src={block.personalInfo.photoUrl}
                  alt="照片"
                  className="w-10 h-10 object-cover rounded mt-1"
                />
              )}
            </>
          ) : (
            <p className="text-xs text-gray-400 italic">未填写</p>
          )}
        </div>
      ) : (
        <div className="text-sm text-gray-700">
          <div className="flex items-center gap-1.5 mb-1">
            {block.content?.category && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                {block.content.category}
              </span>
            )}
            {block.content?.timeSpan && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-600">
                {block.content.timeSpan}
              </span>
            )}
          </div>
          {block.content?.spans && block.content.spans.length > 0 ? (
            <p
              className="text-xs text-gray-600 mt-1 line-clamp-3"
              dangerouslySetInnerHTML={{
                __html: spansToHtml(block.content.spans),
              }}
            />
          ) : (
            <p className="text-xs text-gray-400 italic">未填写</p>
          )}
          {block.content?.bulletPoints && (
            <span className="text-[10px] text-blue-500 mt-1 inline-block">
              • 列表模式
            </span>
          )}
        </div>
      )}

      {/* 底部端口提示 */}
      <p className="text-[10px] text-gray-400 mt-2">
        ← 输入 &nbsp; 输出 →
      </p>
    </div>
  );
}

export default memo(BlockNodeComponent);
