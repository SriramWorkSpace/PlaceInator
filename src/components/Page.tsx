import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { navItemForPath } from "@/lib/nav";

/**
 * Standard page frame: a colored eyebrow naming the section, a serif display
 * title, an optional description, then content -- the recurring
 * "SECTION / Heading" pattern this design follows (see
 * docs/decisions.md#adr-0006--studio-visual-language-superseding-the-github-adjacent-direction).
 *
 * The eyebrow label and its color are derived from the current route via
 * navItemForPath, so every page gets a consistent one automatically instead
 * of each route file passing them in by hand.
 */
export function Page({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  const { pathname } = useLocation();
  const navItem = navItemForPath(pathname);

  return (
    <div className="mx-auto max-w-5xl p-10">
      {navItem && (
        <p className="eyebrow" style={{ color: `var(${navItem.color})` }}>
          {navItem.label}
        </p>
      )}
      <h1 className="display-heading mt-1 text-4xl">{title}</h1>
      {description && (
        <p className="mt-2 max-w-2xl text-sm" style={{ color: "var(--fg-muted)" }}>
          {description}
        </p>
      )}
      <div className="mt-8">{children}</div>
    </div>
  );
}

/**
 * The empty state a feature shows before it has data or before it is built.
 *
 * The specification calls for strong empty states (line 782), and an honest one
 * says what will appear here and what the user should do next -- never a bare
 * "Coming soon".
 */
export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-[var(--radius-panel)] border border-dashed px-6 py-16 text-center"
      style={{ borderColor: "var(--border-strong)", background: "var(--canvas-subtle)" }}
    >
      <p className="text-sm font-medium">{title}</p>
      {hint && (
        <p className="mt-1 max-w-md text-sm" style={{ color: "var(--fg-subtle)" }}>
          {hint}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/**
 * A card with the same "SECTION / Heading" anatomy as Page itself, scaled
 * down for content within a page (the reference's "Weekly Thread" / "Current
 * Care" panels).
 */
export function SectionCard({
  eyebrow,
  eyebrowColor = "var(--accent)",
  title,
  description,
  action,
  children,
}: {
  eyebrow: string;
  eyebrowColor?: string;
  title: string;
  description?: string;
  action?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section
      className="card-hover rounded-[var(--radius-panel)] border p-6"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow" style={{ color: eyebrowColor }}>
            {eyebrow}
          </p>
          <h2 className="display-heading mt-1 text-2xl">{title}</h2>
          {description && (
            <p className="mt-1.5 max-w-lg text-sm" style={{ color: "var(--fg-muted)" }}>
              {description}
            </p>
          )}
        </div>
        {action}
      </div>
      {children && <div className="mt-5">{children}</div>}
    </section>
  );
}
