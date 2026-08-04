import type { ViewType } from "../types";

interface NavItem {
  key: ViewType;
  label: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { key: "new_chat", label: "新聊天", icon: "💬" },
  { key: "resume", label: "简历管理", icon: "📄" },
  { key: "progress", label: "投递进度", icon: "📊" },
];

interface NavSectionProps {
  currentView: ViewType;
  onNavigate: (view: ViewType) => void;
}

export default function NavSection({ currentView, onNavigate }: NavSectionProps) {
  return (
    <nav className="space-y-1 px-2">
      {NAV_ITEMS.map((item) => {
        const active =
          currentView === item.key ||
          (item.key === "new_chat" && currentView === "conversation");
        return (
          <button
            key={item.key}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${
              active
                ? "bg-blue-50 text-blue-700"
                : "text-gray-600 hover:bg-gray-100"
            }`}
            onClick={() => onNavigate(item.key)}
          >
            <span className="text-lg">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
