import { ReactNode } from "react";

/** Measured page enter — opacity + soft rise, direction-aware. */
export function PageTurn({
  turnKey,
  direction = 1,
  children,
  className = "",
}: {
  turnKey: string;
  direction?: 1 | -1;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`view-stage ${className}`.trim()}>
      <div
        key={turnKey}
        className={`view-enter ${direction >= 0 ? "enter-forward" : "enter-back"}`}
      >
        {children}
      </div>
    </div>
  );
}
