import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

import { CloseIcon } from "@/components/icons";

/** A labeled form field, matching the flat/bordered GitHub-adjacent tokens. */
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
      <div className="mt-1">{children}</div>
      {hint && (
        <span className="mt-1 block text-xs" style={{ color: "var(--fg-subtle)" }}>
          {hint}
        </span>
      )}
    </label>
  );
}

const inputStyle = {
  borderColor: "var(--border)",
  background: "var(--canvas)",
  color: "var(--fg)",
};

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded border px-2.5 py-1.5 text-sm outline-none focus:border-[var(--accent)] ${props.className ?? ""}`}
      style={inputStyle}
    />
  );
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`w-full rounded border px-2.5 py-1.5 font-mono text-sm outline-none focus:border-[var(--accent)] ${props.className ?? ""}`}
      style={inputStyle}
    />
  );
}

export function Select(
  props: React.SelectHTMLAttributes<HTMLSelectElement>,
) {
  return (
    <select
      {...props}
      className={`w-full rounded border px-2.5 py-1.5 text-sm outline-none focus:border-[var(--accent)] ${props.className ?? ""}`}
      style={inputStyle}
    />
  );
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" }) {
  const style =
    variant === "primary"
      ? { background: "var(--accent)", color: "var(--accent-fg)", borderColor: "var(--accent)" }
      : { background: "var(--canvas)", color: "var(--fg)", borderColor: "var(--border)" };
  return (
    <button
      {...props}
      className={`rounded border px-3 py-1.5 text-sm font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      style={style}
    />
  );
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
