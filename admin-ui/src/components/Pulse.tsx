/**
 * Live trace line for the command bar. Decorative: it signals "stack is
 * breathing" without pretending to be a metric.
 */
export function Pulse({ className = "" }: { className?: string }) {
  return (
    <span className={`pulse ${className}`.trim()} aria-hidden>
      <svg viewBox="0 0 120 20" preserveAspectRatio="none">
        <path
          className="pulse-line"
          d="M0 12 L14 12 L18 12 L22 5 L26 16 L30 9 L34 12 L52 12 L56 12 L60 7 L64 14 L68 12 L86 12 L90 12 L94 4 L98 15 L102 10 L106 12 L120 12"
        />
      </svg>
    </span>
  );
}
