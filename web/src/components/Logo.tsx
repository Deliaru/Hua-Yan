// 化言的标志：一滴染液里分出三层——客户的场景语言、产品需求语言、化学语言，逐层转译。
// 品牌渐变只用在这里（界面其余部分的颜色规范见 index.css）。
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" role="img" aria-label="化言">
      <defs>
        <linearGradient id="hy-tile" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#2c2c34" />
          <stop offset="1" stopColor="#0e0e12" />
        </linearGradient>
        <linearGradient id="hy-dye" x1="0.2" y1="0" x2="0.8" y2="1">
          <stop offset="0" stopColor="#7ee0ff" />
          <stop offset=".5" stopColor="#5b7cfa" />
          <stop offset="1" stopColor="#b25cf0" />
        </linearGradient>
        <clipPath id="hy-drop">
          <path d="M14 4.6C14 4.6 7.2 11.6 7.2 16.4a6.8 6.8 0 0 0 13.6 0C20.8 11.6 14 4.6 14 4.6Z" />
        </clipPath>
      </defs>
      <rect width="28" height="28" rx="7.5" fill="url(#hy-tile)" />
      <rect x=".5" y=".5" width="27" height="27" rx="7" fill="none" stroke="rgba(255,255,255,.12)" />
      <g clipPath="url(#hy-drop)">
        <rect width="28" height="28" fill="url(#hy-dye)" />
        {/* 三层：两道缝把液滴下部分成三层，自上而下颜色渐深 */}
        <rect y="14.2" width="28" height="1.3" fill="#121216" />
        <rect y="18.3" width="28" height="1.3" fill="#121216" />
        <rect y="15.5" width="28" height="2.8" fill="rgba(255,255,255,.08)" />
      </g>
      <ellipse cx="11.6" cy="11.2" rx="1.1" ry="1.8" fill="rgba(255,255,255,.55)" transform="rotate(28 11.6 11.2)" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <LogoMark />
      <span className="flex flex-col leading-none">
        <span className="text-[15px] font-semibold tracking-[.04em]">化言</span>
        <span className="mt-[3px] text-[9.5px] font-semibold tracking-[.18em] text-ink-3">HUAYAN</span>
      </span>
    </span>
  );
}
