import { useCallback, useMemo, useState } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  BackgroundVariant,
  type Connection as RFConnection,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useResumeState, useResumeDispatch } from "./ResumeContext";
import BlockNode, { type BlockNodeData } from "./BlockNode";
import BlockEditModal from "./BlockEditModal";
import EditorToolbar from "./EditorToolbar";
import DeletableEdge from "./DeletableEdge";

let connIdCounter = 0;
function newConnId(): string {
  connIdCounter++;
  return `conn-${Date.now()}-${connIdCounter}`;
}

const nodeTypes = { blockNode: BlockNode };
const edgeTypes = { deletable: DeletableEdge };

export default function ResumeEditor() {
  const { currentResume, selectedBlockId, selectedConnectionId } = useResumeState();
  const dispatch = useResumeDispatch();

  // 编辑状态：哪个 block 正在被编辑（独立于选中状态）
  const [editingBlockId, setEditingBlockId] = useState<string | null>(null);

  // 当前正在编辑的 block（在弹窗里）
  const editingBlock = useMemo(() => {
    if (!editingBlockId || !currentResume) return null;
    return currentResume.blocks.find((b) => b.id === editingBlockId) ?? null;
  }, [editingBlockId, currentResume]);

  // blocks → ReactFlow nodes
  const nodes: Node<BlockNodeData>[] = useMemo(() => {
    if (!currentResume) return [];
    return currentResume.blocks.map((b) => ({
      id: b.id,
      type: "blockNode",
      position: b.position,
      data: {
        block: b,
        isSelected: selectedBlockId === b.id,
        onEdit: () => setEditingBlockId(b.id),
      },
      draggable: true,
    }));
  }, [currentResume, selectedBlockId]);

  // connections → ReactFlow edges
  const edges: Edge[] = useMemo(() => {
    if (!currentResume) return [];
    return currentResume.connections.map((c) => ({
      id: c.id,
      source: c.fromBlockId,
      target: c.toBlockId,
      type: "deletable",
      selected: c.id === selectedConnectionId,
      data: {
        onDelete: () => {
          dispatch({ type: "DELETE_CONNECTION", connectionId: c.id });
        },
      },
    }));
  }, [currentResume, dispatch, selectedConnectionId]);

  // 连线回调
  const onConnect = useCallback(
    (connection: RFConnection) => {
      if (!connection.source || !connection.target) return;
      const exists = currentResume?.connections.some(
        (c) =>
          c.fromBlockId === connection.source &&
          c.toBlockId === connection.target
      );
      if (exists) return;
      dispatch({
        type: "ADD_CONNECTION",
        connection: {
          id: newConnId(),
          fromBlockId: connection.source,
          toBlockId: connection.target,
        },
      });
    },
    [currentResume, dispatch]
  );

  // 拖拽结束回调
  const onNodeDragStop = useCallback(
    (_event: unknown, node: Node) => {
      dispatch({
        type: "MOVE_BLOCK",
        blockId: node.id,
        position: node.position,
      });
    },
    [dispatch]
  );

  // 点击节点 → 只选中，不弹编辑窗
  const onNodeClick = useCallback(
    (_event: unknown, node: Node) => {
      dispatch({ type: "SELECT_BLOCK", blockId: node.id });
    },
    [dispatch]
  );

  // 点击连线 → 选中连线（显示红色 X）
  const onEdgeClick = useCallback(
    (_event: unknown, edge: Edge) => {
      dispatch({ type: "SELECT_CONNECTION", connectionId: edge.id });
    },
    [dispatch]
  );

  // 点击画布空白处清除选中
  const onPaneClick = useCallback(() => {
    dispatch({ type: "CLEAR_SELECTION" });
  }, [dispatch]);

  if (!currentResume) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50">
        <p className="text-gray-400 text-lg">请选择或创建一份简历</p>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <EditorToolbar />
      <div className="flex-1 bg-gray-50">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onConnect={onConnect}
          onNodeDragStop={onNodeDragStop}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          snapToGrid
          snapGrid={[20, 20]}
          deleteKeyCode={null}
          multiSelectionKeyCode={null}
        >
          <Controls />
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
        </ReactFlow>
      </div>

      {/* 文本块编辑弹窗（通过编辑按钮触发，而非选中） */}
      {editingBlock && (
        <BlockEditModal
          block={editingBlock}
          resumeId={currentResume.id}
          onClose={() => setEditingBlockId(null)}
        />
      )}
    </div>
  );
}
