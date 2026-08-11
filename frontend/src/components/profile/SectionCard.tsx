import type { ReactNode } from "react";

interface SectionCardProps {
  title: string;
  /** 传入则标题右侧显示「添加」按钮 */
  onAdd?: () => void;
  addLabel?: string;
  children: ReactNode;
}

export default function SectionCard({
  title,
  onAdd,
  addLabel = "添加",
  children,
}: SectionCardProps) {
  return (
    <section className="bg-white rounded-lg border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-gray-800">{title}</h2>
        {onAdd && (
          <button
            type="button"
            onClick={onAdd}
            className="px-3 py-1.5 text-sm font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-md transition"
          >
            + {addLabel}
          </button>
        )}
      </div>
      {children}
    </section>
  );
}
