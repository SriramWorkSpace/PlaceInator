import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

import { CloseIcon } from "@/components/icons";

/** A labeled form field. */
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium">{label}</span>
      <div className="mt-1.5">{children}</div>
      {hint && (
        <span className="mt-1.5 block text-xs" style={{ color: "var(--fg-subtle)" }}>
          {hint}
        </span>
      )}
    </label>
  );
}

const controlStyle = {
  borderColor: "var(--border)",
  background: "var(--canvas)",
  color: "var(--fg)",
};

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`field-control w-full border px-3.5 py-2.5 text-sm outline-none ${props.className ?? ""}`}
      style={controlStyle}
    />
  );
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`field-control w-full border px-3.5 py-2.5 font-mono text-sm outline-none ${props.className ?? ""}`}
      style={controlStyle}
    />
  );
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`field-control w-full border px-3.5 py-2.5 text-sm outline-none ${props.className ?? ""}`}
      style={controlStyle}
    />
  );
}

/**
 * Pill buttons at a 48px comfort target, in the three states the reference
 * shows: solid primary, outlined secondary, and a soft tinted variant for a
 * clearly-present-but-unavailable action (not just a dimmed primary).
 */
export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "soft";
}) {
  const style = {
    primary: { background: "var(--accent)", color: "var(--accent-fg)", borderColor: "var(--accent)" },
    secondary: { background: "var(--canvas)", color: "var(--fg)", borderColor: "var(--border-strong)" },
    soft: { background: "var(--accent-subtle)", color: "var(--accent)", borderColor: "transparent" },
  }[variant];

  return <button {...props} className={`btn ${className}`} style={style} />;
}

export function ErrorText({
  children,
  onDismiss,
}: {
  children: ReactNode;
  /** When provided, renders a close button that clears the error (e.g. a
   * mutation's reset()) so a stale message doesn't linger after retrying. */
  onDismiss?: () => void;
}) {
  return (
    <p
      className="selectable flex items-start gap-1.5 text-xs"
      style={{ color: "var(--danger)" }}
    >
      <span className="flex-1">{children}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="shrink-0 opacity-70 hover:opacity-100"
        >
          <CloseIcon width={14} height={14} />
        </button>
      )}
    </p>
  );
}
