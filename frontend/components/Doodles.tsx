import type { CSSProperties } from "react";

/**
 * Small hand-drawn accent marks - currentColor strokes, deliberately
 * slightly irregular paths rather than perfect geometry, so they read as
 * doodled rather than iconography. Used sparingly as texture, never as
 * functional UI (no click targets, no meaning encoded in them) - decoration
 * only, matching this app's no-icon-library rule (hand-rolled SVG, same
 * as BrandMarks.tsx).
 */

interface DoodleProps {
  className?: string;
  style?: CSSProperties;
}

export function DoodleUnderline({ className, style, width = 120 }: DoodleProps & { width?: number }) {
  return (
    <svg
      className={className}
      style={style}
      width={width}
      height="14"
      viewBox="0 0 120 14"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M2 8.5C14 3.5 24 11.5 36 7C48 2.5 58 11 70 7.5C82 4 92 10.5 104 6.5C110 4.5 114 5.5 118 7"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function DoodleCircle({ className, style, size = 64 }: DoodleProps & { size?: number }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <path
        d="M32 6C46 5 56 15 57 29C58 44 47 56 32 57C17 58 6 47 6 32C6 18 16 8 30 7"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function DoodleArrow({ className, style, size = 56 }: DoodleProps & { size?: number }) {
  return (
    <svg
      className={className}
      style={style}
      width={size}
      height={size * 0.7}
      viewBox="0 0 80 56"
      fill="none"
      aria-hidden="true"
    >
      <path d="M4 10C22 8 40 34 58 40" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path
        d="M44 36C49 37 55 39 59 41C57 36 55 30 54 25"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function DoodleSpark({ className, style, size = 22 }: DoodleProps & { size?: number }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 2.5C12 8 12 8 12 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M12 16C12 21.5 12 21.5 12 21.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M2.5 12C8 12 8 12 8 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M16 12C21.5 12 21.5 12 21.5 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M5 5C8.5 8.5 8.5 8.5 8.5 8.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M15.5 15.5C19 19 19 19 19 19" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function DoodleLoop({ className, style, size = 40 }: DoodleProps & { size?: number }) {
  return (
    <svg className={className} style={style} width={size} height={size * 0.6} viewBox="0 0 60 36" fill="none" aria-hidden="true">
      <path
        d="M2 30C10 8 20 4 26 14C32 24 22 30 18 22C14 14 26 4 38 8C48 11 50 20 58 16"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function DoodleCheck({ className, style, size = 22 }: DoodleProps & { size?: number }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 12.5C7 15.5 8.5 17.5 9.5 19C12 13.5 15.5 8 20 4"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function DoodleDivider({ className, style, width = 80 }: DoodleProps & { width?: number }) {
  return (
    <svg className={className} style={style} width={width} height="10" viewBox="0 0 80 10" fill="none" aria-hidden="true">
      <path
        d="M1 5C10 1 16 9 25 5C34 1 40 9 49 5C58 1 64 9 73 5C76 3.5 78 4 79 5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function DoodleWave({ className, style, width = 46 }: DoodleProps & { width?: number }) {
  return (
    <svg className={className} style={style} width={width} height="16" viewBox="0 0 46 16" fill="none" aria-hidden="true">
      <path
        d="M1 8C4 2 7 2 9 8C11 14 14 14 16 8C18 2 21 2 23 8C25 14 28 14 30 8C32 2 35 2 37 8C39 14 42 14 45 8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}
