interface MetricCardsProps {
  total: number;
  active: number;
  offer: number;
  rejected: number;
  monthly: number;
}

export default function MetricCards({
  total,
  active,
  offer,
  rejected,
  monthly,
}: MetricCardsProps) {
  const items = [
    { label: "全部记录", value: total, accent: true },
    { label: "进行中", value: active, accent: false },
    { label: "已获 Offer", value: offer, accent: false },
    { label: "已拒绝", value: rejected, accent: false },
    { label: "本月投递", value: monthly, accent: false },
  ];

  return (
    <div className="grid grid-cols-5 gap-4">
      {items.map((item) => (
        <div
          key={item.label}
          className="bg-white rounded-2xl border border-slate-200 shadow-sm px-5 py-4"
        >
          <div
            className={`text-3xl font-bold ${
              item.accent ? "text-blue-600" : "text-slate-900"
            }`}
          >
            {item.value}
          </div>
          <div className="text-sm text-slate-500 mt-1">{item.label}</div>
        </div>
      ))}
    </div>
  );
}