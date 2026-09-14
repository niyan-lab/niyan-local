/** Layered field: engineering grid, slow light, and paper grain. */
export function Atmosphere({ className = "" }: { className?: string }) {
  return (
    <div className={`atmosphere ${className}`.trim()} aria-hidden>
      <span className="atmosphere-grid" />
      <span className="atmosphere-light" />
      <span className="atmosphere-grain" />
    </div>
  );
}
