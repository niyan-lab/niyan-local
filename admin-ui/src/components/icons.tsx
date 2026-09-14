/** 16px stroke icons — single weight, optically aligned to the nav baseline. */
import { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Glyph({ children, ...rest }: IconProps) {
  return (
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.35"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconDashboard = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M2.5 9.5a5.5 5.5 0 0 1 11 0" />
    <path d="M8 9.5 10.75 6" />
    <path d="M2.5 12.5h11" />
  </Glyph>
);

export const IconModels = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M8 1.9 14 5v6l-6 3.1L2 11V5z" />
    <path d="M2 5l6 3.1L14 5" />
    <path d="M8 8.1v6" />
  </Glyph>
);

export const IconProviders = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M4.6 12.5a2.85 2.85 0 0 1-.35-5.68 3.9 3.9 0 0 1 7.5-1.06A2.95 2.95 0 0 1 11.9 12.5z" />
  </Glyph>
);

export const IconGateway = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M2 8h3.2" />
    <path d="M10.8 8H14" />
    <rect x="5.2" y="4.6" width="5.6" height="6.8" rx="1.5" />
  </Glyph>
);

export const IconPolicy = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M8 1.9 13.2 4v4.1c0 3-2.2 5.1-5.2 6-3-.9-5.2-3-5.2-6V4z" />
    <path d="M5.9 7.9 7.4 9.4l2.9-3" />
  </Glyph>
);

export const IconGuardrails = (p: IconProps) => (
  <Glyph {...p}>
    <rect x="2.6" y="7" width="10.8" height="6.4" rx="1.6" />
    <path d="M5.4 7V5.2a2.6 2.6 0 0 1 5.2 0V7" />
  </Glyph>
);

export const IconVectors = (p: IconProps) => (
  <Glyph {...p}>
    <circle cx="4" cy="4.2" r="1.7" />
    <circle cx="12" cy="6.4" r="1.7" />
    <circle cx="6.4" cy="12" r="1.7" />
    <path d="M5.5 5.3 10.5 5.9" />
    <path d="M4.7 5.8 5.9 10.4" />
  </Glyph>
);

export const IconLoad = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M2 12.5V9.8" />
    <path d="M5.7 12.5V6.4" />
    <path d="M9.4 12.5V8.1" />
    <path d="M13.1 12.5V3.5" />
  </Glyph>
);

export const IconObservability = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M1.8 8s2.4-4.1 6.2-4.1S14.2 8 14.2 8s-2.4 4.1-6.2 4.1S1.8 8 1.8 8z" />
    <circle cx="8" cy="8" r="1.7" />
  </Glyph>
);

export const IconSettings = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M3 4.6h10" />
    <path d="M3 11.4h10" />
    <circle cx="6.2" cy="4.6" r="1.5" />
    <circle cx="10.2" cy="11.4" r="1.5" />
  </Glyph>
);

export const IconSearch = (p: IconProps) => (
  <Glyph {...p}>
    <circle cx="7.2" cy="7.2" r="4.3" />
    <path d="m10.5 10.5 3 3" />
  </Glyph>
);

export const IconArrow = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M3.5 8h9" />
    <path d="m9 4.5 3.5 3.5L9 11.5" />
  </Glyph>
);
