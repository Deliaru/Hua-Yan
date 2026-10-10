// 复制自 JUE wp/e 的 web/src/components/Controls.tsx（只保留分段切换）
// 分段切换。dark：主导航用黑色选中态；默认白色选中态。
export function Segmented<K extends string | number>({
  items,
  value,
  onChange,
  dark,
  size = "md",
  wrap,
}: {
  items: readonly (readonly [K, string])[];
  value: K;
  onChange: (k: K) => void;
  dark?: boolean;
  size?: "sm" | "md";
  wrap?: boolean;
}) {
  return (
    <div className={`pill inline-flex p-[3px] ${wrap ? "flex-wrap gap-y-0.5 !rounded-[16px]" : ""} ${size === "sm" ? "text-[12px]" : "text-[13px]"}`}>
      {items.map(([k, label]) => (
        <button
          key={k}
          onClick={() => onChange(k)}
          className={`whitespace-nowrap rounded-full transition-all duration-200 ${size === "sm" ? "px-2.5 py-0.5" : "px-3.5 py-1"} ${
            value === k ? (dark ? "bg-ink text-white shadow-[0_2px_8px_rgba(0,0,0,.2)]" : "seg-on") : "text-black/55 hover:text-black/80"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
