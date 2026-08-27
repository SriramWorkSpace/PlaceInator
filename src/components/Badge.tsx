import type { ReactNode } from "react";

export type BadgeTone = "accent" | "success" | "warning" | "danger" | "neutral";

const TONE_COLOR: Record<BadgeTone, string> = {
  accent: "var(--accent)",
  success: "var(--success)",
  warning: "var(--warning)",
  danger: "var(--danger)",
  neutral: "var(--fg-subtle)",
};

/**
 * The pill badge every route already hand-rolls with an identical inline
 * `style={{ background: "var(--accent-subtle)", ... borderRadius:
 * "var(--radius-pill)" }}` block (Dashboard, Jobs, Resumes, Tailor, Career,
 * Outreach, Placement, Settings all had their own copy). `accent` matches
 * that existing shape exactly (px-2.5 py-0.5 text-xs font-medium,
 * accent-subtle background) so swapping it in is a pure refactor with no
 * visual diff; the other tones extend the same recipe via `color-mix`,
 * the same technique AppShell.tsx already uses for its nav icon badges
 * (`color-mix(in srgb, var(--x) 20%, transparent)`) rather than inventing
 * new hardcoded subtle-background hexes.
 *
 * `tag` matches Jobs.tsx's smaller uppercase source-tag treatment
 * (`--canvas`/`--fg-subtle`, text-[10px] uppercase) -- a second, deliberately
 * quieter shape for provenance/metadata rather than a status claim.
 */
export function Badge({
  tone = "accent",
  size = "default",
  icon,
  /** 0-100. When set, renders a left-to-right fill inside the pill instead
   * of a flat tint -- a lightweight gauge for match-score badges (Jobs,
   * Outreach) rather than a separate chart component for one number. */
  fillPercent,
  children,
}: {
  tone?: BadgeTone;
  size?: "default" | "tag";
  icon?: ReactNode;
  fillPercent?: number;
  children: ReactNode;
}) {
  const color = TONE_COLOR[tone];
  const subtleBackground =
    tone === "accent"
      ? "var(--accent-subtle)"
      : tone === "neutral"
        ? "var(--canvas-inset)"
        : `color-mix(in srgb, ${color} 16%, transparent)`;

  if (size === "tag") {
    return (
      <span
        className="rounded-[var(--radius-pill)] px-1.5 py-0.5 text-[10px] uppercase tracking-wide"
        style={{ background: "var(--canvas)", color: "var(--fg-subtle)" }}
      >
        {children}
      </span>
    );
  }

  const background =
    fillPercent === undefined
      ? subtleBackground
      : `linear-gradient(to right, color-mix(in srgb, ${color} 30%, transparent) ${fillPercent}%, ${subtleBackground} ${fillPercent}%)`;

  return (
    <span
      className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] px-2.5 py-0.5 text-xs font-medium"
      style={{ background, color: tone === "neutral" ? "var(--fg-subtle)" : color }}
    >
      {icon}
      {children}
    </span>
  );
}
