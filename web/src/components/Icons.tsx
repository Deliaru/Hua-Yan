// 线性图标（SF Symbols 风格，1.6 描边）。
const base = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.6,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

export const ArrowUp = () => <svg {...base}><path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" /></svg>;
export const Plus = () => <svg {...base}><path d="M8 3v10M3 8h10" /></svg>;
export const ChevronDown = () => <svg {...base} width={12} height={12}><path d="m4 6 4 4 4-4" /></svg>;
export const ChevronRight = ({ open }: { open?: boolean }) => (
  <svg {...base} width={12} height={12} style={{ transform: open ? "rotate(90deg)" : undefined, transition: "transform .15s" }}>
    <path d="m6 4 4 4-4 4" />
  </svg>
);
export const Refresh = () => <svg {...base}><path d="M13 8a5 5 0 1 1-1.5-3.55M13 2.5V5h-2.5" /></svg>;
export const Close = () => <svg {...base} width={12} height={12}><path d="m4 4 8 8M12 4l-8 8" /></svg>;
export const Info = () => <svg {...base} width={13} height={13}><circle cx="8" cy="8" r="6.2" /><path d="M8 7.2v3.6M8 5.1v.1" /></svg>;
export const Lock = () => <svg {...base} width={12} height={12}><rect x="3.5" y="7" width="9" height="6.5" rx="1.5" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" /></svg>;
