// 化言的标志（品牌标，web/public/logo-mark.png）；字标「化言」用页面文字写，浅色界面上看得清。
export function LogoMark({ size = 28 }: { size?: number }) {
  return <img src="./logo-mark.png" width={size} height={size} alt="化言" />;
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
