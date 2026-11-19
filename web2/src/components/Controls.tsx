// 控件：弹出菜单。
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

// 点击按钮弹出、点击外部关闭的菜单。
export function Popover({ trigger, children, align = "left" }: {
  trigger: (toggle: () => void) => React.ReactNode;
  children: (close: () => void) => React.ReactNode;
  align?: "left" | "right";
}) {
  // 菜单挂到 body 上按按钮位置定位，不被侧栏等滚动容器裁掉
  const [at, setAt] = useState<DOMRect | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!at) return;
    const away = (e: MouseEvent) => ref.current?.contains(e.target as Node) || pop.current?.contains(e.target as Node) || setAt(null);
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [at]);
  return (
    <div ref={ref} className="relative min-w-0">
      {trigger(() => setAt(at ? null : ref.current!.getBoundingClientRect()))}
      {at && createPortal(
        <div ref={pop} className="popover anim-fade" style={{ position: "fixed", top: at.bottom + 6,
          ...(align === "right" ? { right: window.innerWidth - at.right } : { left: at.left }) }}>
          {children(() => setAt(null))}
        </div>, document.body)}
    </div>
  );
}
