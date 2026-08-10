import { memo } from "react";
import {
  BaseEdge,
  getSmoothStepPath,
  type EdgeProps,
} from "@xyflow/react";

type DeletableEdgeData = {
  onDelete?: () => void;
};

function DeletableEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  selected,
  data,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  });

  const edgeData = data as DeletableEdgeData | undefined;

  return (
    <>
      {/* 连线：选中时变蓝加粗，否则灰色 */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: selected ? "#3b82f6" : "#94a3b8",
          strokeWidth: selected ? 3 : 2,
          cursor: "pointer",
        }}
      />

      {/* 选中时在连线中间显示红色 ✕ 删除按钮 */}
      {selected && edgeData?.onDelete && (
        <foreignObject
          width={28}
          height={28}
          x={labelX - 14}
          y={labelY - 14}
          className="overflow-visible"
          style={{ pointerEvents: "all" }}
        >
          <button
            className="w-7 h-7 rounded-full bg-red-500 text-white flex items-center justify-center text-sm font-bold shadow-lg hover:bg-red-600 hover:scale-110 transition-transform cursor-pointer"
            title="删除连线"
            onClick={(e) => {
              e.stopPropagation();
              edgeData.onDelete?.();
            }}
          >
            ✕
          </button>
        </foreignObject>
      )}
    </>
  );
}

export default memo(DeletableEdgeComponent);
