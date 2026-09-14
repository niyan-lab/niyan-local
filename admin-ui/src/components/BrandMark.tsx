/** Official cube mark from niyan.tech, always paired with lowercase "niyan". */
export function BrandMark({
  size = 28,
  sub,
  className = "",
}: {
  size?: number;
  sub?: string;
  className?: string;
}) {
  return (
    <span className={`brand-mark ${sub ? "brand-mark--stacked" : ""} ${className}`.trim()}>
      <img className="brand-glyph" src="/niyan-mark.png" alt="" width={size} height={size} />
      <span className="brand-text">
        <span className="brand-word">niyan</span>
        {sub ? <span className="brand-sub">{sub}</span> : null}
      </span>
    </span>
  );
}
