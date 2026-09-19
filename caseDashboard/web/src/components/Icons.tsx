/** Hand-rolled 16px icon set: avoids an icon dependency for ~12 glyphs. */
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;

const base = (props: P) => ({
  width: 16,
  height: 16,
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  ...props,
});

export const IconGrid = (p: P) => (
  <svg {...base(p)}>
    <path d="M2 6h12M2 10h12M6 2v12M10 2v12" />
    <rect x="2" y="2" width="12" height="12" rx="1.5" />
  </svg>
);

export const IconLink = (p: P) => (
  <svg {...base(p)}>
    <path d="M6.5 9.5 9.5 6.5" />
    <path d="M5.5 11 4 12.5a2.5 2.5 0 0 1-3.5-3.5L2 7.5" />
    <path d="M10.5 5 12 3.5A2.5 2.5 0 0 1 15.5 7L14 8.5" />
  </svg>
);

export const IconSphere = (p: P) => (
  <svg {...base(p)}>
    <circle cx="8" cy="8" r="5.5" />
    <ellipse cx="8" cy="8" rx="5.5" ry="2.2" />
    <path d="M8 2.5v11" />
  </svg>
);

/**
 * A scatter of dots -- the particle side.  Filled rather than stroked: at 14px
 * an outlined circle of this size just reads as a blob, and the size spread is
 * what says "many particles" instead of "a bullet list".
 */
export const IconParticles = (p: P) => (
  <svg {...base(p)}>
    <circle cx="5" cy="4.8" r="2.2" fill="currentColor" stroke="none" />
    <circle cx="11.6" cy="4.4" r="1.3" fill="currentColor" stroke="none" />
    <circle cx="8.5" cy="9.6" r="2.4" fill="currentColor" stroke="none" />
    <circle cx="3" cy="12.2" r="1.5" fill="currentColor" stroke="none" />
    <circle cx="13" cy="12.4" r="1.2" fill="currentColor" stroke="none" />
  </svg>
);

export const IconCheck = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 8.5 6.5 12 13 4.5" />
  </svg>
);

export const IconAlert = (p: P) => (
  <svg {...base(p)}>
    <path d="M8 2.8 14.5 13.5h-13z" />
    <path d="M8 6.5v3M8 11.6v.6" />
  </svg>
);

export const IconCross = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </svg>
);

export const IconInfo = (p: P) => (
  <svg {...base(p)}>
    <circle cx="8" cy="8" r="5.8" />
    <path d="M8 7.4v3.4M8 5.3v.6" />
  </svg>
);

export const IconDiff = (p: P) => (
  <svg {...base(p)}>
    <path d="M4.5 2v12M11.5 2v12" />
    <path d="M2.5 5.5h4M9.5 10.5h4" />
  </svg>
);

export const IconUndo = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 8a5 5 0 1 0 5-5" />
    <path d="M2.2 4.2 3 8l3.6-1.3" />
  </svg>
);

export const IconFile = (p: P) => (
  <svg {...base(p)}>
    <path d="M9 1.8H4.5a1 1 0 0 0-1 1v10.4a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V5.3z" />
    <path d="M9 1.8v3.5h3.5" />
  </svg>
);

/** A half-filled disc, the usual "which of the two looks" mark.  The filled
 * half is drawn as a path rather than a clipped rect so it inherits
 * `currentColor` and needs no `fill-rule` gymnastics at 13px. */
export const IconTheme = (p: P) => (
  <svg {...base(p)}>
    <circle cx="8" cy="8" r="6.2" />
    <path d="M8 1.8a6.2 6.2 0 0 1 0 12.4z" fill="currentColor" stroke="none" />
  </svg>
);

/** The six-dot drag handle.  Filled dots rather than stroked: at the 12px it
 * is used at, an outlined circle of this radius fills in and the whole thing
 * reads as one grey smudge. */
export const IconGrip = (p: P) => (
  <svg {...base(p)}>
    <circle cx="6" cy="4" r="1.15" fill="currentColor" stroke="none" />
    <circle cx="10" cy="4" r="1.15" fill="currentColor" stroke="none" />
    <circle cx="6" cy="8" r="1.15" fill="currentColor" stroke="none" />
    <circle cx="10" cy="8" r="1.15" fill="currentColor" stroke="none" />
    <circle cx="6" cy="12" r="1.15" fill="currentColor" stroke="none" />
    <circle cx="10" cy="12" r="1.15" fill="currentColor" stroke="none" />
  </svg>
);

export const IconChevron = (p: P) => (
  <svg {...base(p)}>
    <path d="M5.5 6.5 8 9.5l2.5-3" />
  </svg>
);

export const IconFolderPlus = (p: P) => (
  <svg {...base(p)}>
    <path d="M2.2 12.6V4.4a1 1 0 0 1 1-1h2.9l1.5 1.9h5a1 1 0 0 1 1 1v6.3a1 1 0 0 1-1 1H3.2a1 1 0 0 1-1-1z" />
    <path d="M8 7.5v3.4M6.3 9.2h3.4" />
  </svg>
);

export const IconFolder = (p: P) => (
  <svg {...base(p)}>
    <path d="M2.2 12.6V4.4a1 1 0 0 1 1-1h2.9l1.5 1.9h5a1 1 0 0 1 1 1v6.3a1 1 0 0 1-1 1H3.2a1 1 0 0 1-1-1z" />
  </svg>
);

export const IconArrowUp = (p: P) => (
  <svg {...base(p)}>
    <path d="M8 13V3.5" />
    <path d="M4 7.5 8 3.5l4 4" />
  </svg>
);

export const IconTarget = (p: P) => (
  <svg {...base(p)}>
    <circle cx="8" cy="8" r="5.5" />
    <circle cx="8" cy="8" r="1.8" />
  </svg>
);

export const IconGlobe = (p: P) => (
  <svg {...base(p)}>
    <circle cx="8" cy="8" r="5.8" />
    <path d="M2.2 8h11.6" />
    <path d="M8 2.2c1.7 1.7 2.5 3.7 2.5 5.8S9.7 12.1 8 13.8C6.3 12.1 5.5 10.1 5.5 8S6.3 3.9 8 2.2Z" />
  </svg>
);

export const IconSpinner = (p: P) => (
  <svg {...base(p)} className={`anim-spin ${p.className ?? ""}`}>
    <path d="M8 2.2a5.8 5.8 0 1 0 5.8 5.8" />
  </svg>
);
