import type { CSSProperties, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

import { CloseIcon } from "@/components/icons";
import { Select as ThemedSelect } from "@/components/ui/select";

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

/** Re-exported from ui/select.tsx: a themed replacement for the browser's
 * own unstylable dropdown popup, kept behind this same import path
 * (`@/components/Form`) so every existing call site across the app picks
 * up the theming with no changes of its own. */
export const Select = ThemedSelect;

type ButtonVariant = "primary" | "secondary" | "soft" | "danger";

/** Every color here is a --btn-* custom property consumed by .btn's own
 * CSS (styles/index.css), never a literal color applied directly -- see
 * that file's comment for why (inline `style` would otherwise always
 * outrank the `:hover` rules that read these). Each value is itself built
 * from --accent/--danger, so a button never needs to know which of the
 * four accent palettes (src/lib/palette.ts) or which theme is active.
 *
 * primary/danger are already solid-colored at rest, so their hover --btn-
 * fill is left equal to --btn-bg (no color swap) -- the lift + glowing
 * shadow alone read as "hovered" without adding a pointless same-color
 * transition. secondary/soft start outlined/tinted, so hover fills them in
 * solid with --accent, same as the outline-to-filled transformation this
 * treatment is built around. */
const VARIANT_STYLE: Record<ButtonVariant, CSSProperties> = {
  primary: {
    "--btn-bg": "var(--accent)",
    "--btn-fg": "var(--accent-fg)",
    "--btn-fill": "var(--accent)",
    "--btn-fill-fg": "var(--accent-fg)",
    "--btn-glow": "color-mix(in srgb, var(--accent) 45%, transparent)",
  } as CSSProperties,
  secondary: {
    "--btn-bg": "var(--canvas)",
    "--btn-fg": "var(--fg)",
    "--btn-fill": "var(--accent)",
    "--btn-fill-fg": "var(--accent-fg)",
    "--btn-glow": "color-mix(in srgb, var(--accent) 45%, transparent)",
  } as CSSProperties,
  soft: {
    "--btn-bg": "var(--accent-subtle)",
    "--btn-fg": "var(--accent)",
    "--btn-fill": "var(--accent)",
    "--btn-fill-fg": "var(--accent-fg)",
    "--btn-glow": "color-mix(in srgb, var(--accent) 45%, transparent)",
  } as CSSProperties,
  danger: {
    "--btn-bg": "var(--danger)",
    "--btn-fg": "#ffffff",
    "--btn-fill": "var(--danger)",
    "--btn-fill-fg": "#ffffff",
    "--btn-glow": "color-mix(in srgb, var(--danger) 45%, transparent)",
  } as CSSProperties,
};

/**
 * Pill buttons at a 48px+ comfort target. Four states: solid primary,
 * outlined secondary, a soft tinted variant for a clearly-present-but-
 * unavailable action (not just a dimmed primary), and danger for the one or
 * two truly destructive actions in the app (delete account) -- same solid
 * treatment as primary, `--danger` instead of `--accent`, so it reads as
 * "the same kind of commitment as the main action" rather than a lesser or
 * decorative button.
 *
 * Hover is a floating-card lift: the button rises and its shadow grows and
 * picks up the variant's own color as a soft glow (see .btn in
 * styles/index.css).
 */
export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
}) {
  return <button {...props} className={`btn ${className}`} style={VARIANT_STYLE[variant]} />;
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
