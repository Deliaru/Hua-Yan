// 控件：分段控件（macOS 样式：灰轨道 + 白滑块）、弹出菜单。
import { useEffect, useRef, useState } from "react";

export function Segmented<K extends string | number>({
  items,
  value,
  onChange,
  wide,
}: {
  items: readonly (readonly [K, string])[];
  value: K;
  onChange: (k: K) => void;
  wide?: boolean;
}) {
  return (
    <div className="inline-flex rounded-[9px] bg-fill p-[2px]">
      {items.map(([k, label]) => (
        <button
          key={k}
          type="button"
          onClick={() => onChange(k)}
          className={`h-7 whitespace-nowrap rounded-[7px] text-[13px] transition-all duration-150 ${wide ? "px-5" : "px-3"} ${
            value === k
              ? "bg-white font-semibold text-ink shadow-[0_1px_3px_rgba(0,0,0,.12),0_0_0_.5px_rgba(0,0,0,.04)]"
              : "text-ink-2 hover:text-ink"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// 点击按钮弹出、点击外部关闭的菜单。
export function Popover({ trigger, children, align = "left" }: {
  trigger: (toggle: () => void) => React.ReactNode;
  children: (close: () => void) => React.ReactNode;
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => ref.current?.contains(e.target as Node) || setOpen(false);
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  return (
    <div ref={ref} className="relative">
      {trigger(() => setOpen(!open))}
      {open && (
        <div className={`popover anim-fade top-full mt-1.5 ${align === "right" ? "right-0" : "left-0"}`}>
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}
