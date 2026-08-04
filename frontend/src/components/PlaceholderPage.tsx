interface PlaceholderPageProps {
  title: string;
}

export default function PlaceholderPage({ title }: PlaceholderPageProps) {
  return (
    <div className="flex items-center justify-center h-full">
      <p className="text-gray-400 text-lg">
        {title} — 该功能将在后续版本开发
      </p>
    </div>
  );
}
