// 控件：弹出菜单。
import { useEffect, useRef, useState } from "react";

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
