// 复制自 JUE wp/e 的 web/src/components/Backdrop.tsx
// 全屏天色背景：黎明渐变 + 缓慢漂移的云层。
export function Backdrop() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(120% 70% at 75% 110%, rgba(255,196,150,.75) 0%, rgba(255,214,186,.35) 35%, transparent 65%)," +
            "linear-gradient(180deg, #4d74a6 0%, #7c9fca 30%, #b3c7de 62%, #e6dccf 100%)",
        }}
      />
      <svg className="anim-drift absolute inset-y-0 left-0 h-full w-[300%] opacity-80" preserveAspectRatio="none">
        <filter id="clouds" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.0016 0.006" numOctaves="5" seed="11" stitchTiles="stitch" />
          <feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  1.8 0 0 0 -0.78" />
          <feGaussianBlur stdDeviation="6" />
        </filter>
        <rect width="100%" height="100%" filter="url(#clouds)" />
      </svg>
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-white/20" />
    </div>
  );
}
