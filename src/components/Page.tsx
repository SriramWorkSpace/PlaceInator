import type { ReactNode } from "react";

/** Standard page frame: title, optional description, then content. */
export function Page({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-5xl p-8">
      <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
      {description && (
        <p className="mt-1 text-sm" style={{ color: "var(--fg-muted)" }}>
          {description}
        </p>
      )}
      <div className="mt-6">{children}</div>
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
      className="flex flex-col items-center justify-center rounded-md border border-dashed px-6 py-16 text-center"
      style={{ borderColor: "var(--border)" }}
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
