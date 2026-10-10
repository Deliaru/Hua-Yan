// 分段切换，源自 JUE wp/e 的 web/src/components/Controls.tsx；样式按 Hark 顶部导航胶囊重做：
// 白 55% 磨砂胶囊，内边距 2，选中项为实心 ink。
export function Segmented<K extends string | number>({
  items,
  value,
  onChange,
  size = "md",
  wrap,
}: {
  items: readonly (readonly [K, string])[];
  value: K;
  onChange: (k: K) => void;
  size?: "sm" | "md";
  wrap?: boolean;
}) {
  return (
    <div className={`pill inline-flex p-[2px] ${wrap ? "flex-wrap !rounded-[20px]" : ""}`}>
      {items.map(([k, label]) => (
        <button
          key={k}
          onClick={() => onChange(k)}
          className={`press whitespace-nowrap rounded-full font-medium transition-colors duration-200 ${
            size === "sm" ? "h-8 px-3 text-[13px]" : "h-11 px-4 text-[15px]"} ${
            value === k ? "seg-on" : "text-ink/50 hover:text-ink/80"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
