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

// 侧栏导航（17px）
const nav = { ...base, width: 17, height: 17, strokeWidth: 1.5 };
export const NavDesk = () => <svg {...nav}><rect x="2" y="3" width="12" height="10" rx="2" /><path d="M2 6.5h12M6 6.5V13" /></svg>;
export const NavJue = () => <svg {...nav}><path d="M1.5 11h2.5l2-6 2.5 8 2-5h4" /></svg>;
export const NavLayers = () => <svg {...nav}><path d="m8 2 6 3-6 3-6-3 6-3Z" /><path d="m2 8 6 3 6-3M2 11l6 3 6-3" /></svg>;
export const NavEval = () => <svg {...nav}><path d="M2.5 13.5h11M4.5 11V7.5M8 11V4M11.5 11V6" /></svg>;
export const NavLedger = () => <svg {...nav}><circle cx="8" cy="6.5" r="4" /><path d="m5.6 9.8-1 4.2L8 12.4l3.4 1.6-1-4.2" /></svg>;
export const Gauge = () => <svg {...base} width={13} height={13}><circle cx="8" cy="8" r="6" /><path d="M8 8 10.5 5.5" /></svg>;
