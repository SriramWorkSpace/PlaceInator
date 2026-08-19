import { AnimatePresence, motion } from "motion/react";
import type { MouseEvent, ReactNode } from "react";

/**
 * A track-and-thumb toggle (source: a 21st.dev component), adapted --
 * retokenized onto this project's design system rather than left with
 * shadcn's default `bg-card-foreground`/`bg-background` classes, which
 * don't exist as tokens here (same reasoning as the date-picker
 * integration: this app's CSS custom properties, not shadcn's default
 * palette names).
 *
 * One real bug fixed, not just restyled: the source rendered the on/off
 * icon as two conditionally-mounted `motion.div`s with `exit` props but no
 * `AnimatePresence` wrapper. Framer Motion only animates an unmount when
 * the exiting element is inside `AnimatePresence` -- without it, `exit`
 * is dead code: the old icon just vanishes and only the new icon's
 * `initial` -> `animate` plays. Added the wrapper so the rotate-out
 * actually happens.
 *
 * `onToggle` receives the click event (not just `() => void`) so a
 * consumer can read `clientX`/`clientY` -- src/lib/theme.ts uses this to
 * anchor its circular reveal at the exact point clicked.
 */

type SwitchProps = {
  value: boolean;
  onToggle: (event: MouseEvent<HTMLButtonElement>) => void;
  iconOn: ReactNode;
  iconOff: ReactNode;
  className?: string;
};

export function Switch({ value, onToggle, iconOn, iconOff, className = "" }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      onClick={onToggle}
      className={`flex w-12 cursor-pointer rounded-full border p-0.5 transition-colors ${
        value ? "justify-end" : "justify-start"
      } ${className}`}
      style={{ background: "var(--canvas-inset)", borderColor: "var(--border)" }}
    >
      <motion.div
        className="flex size-6 items-center justify-center rounded-full"
        style={{ background: "var(--canvas)", boxShadow: "var(--shadow-card)", color: "var(--fg-muted)" }}
        layout
        transition={{ type: "spring", duration: 0.6, bounce: 0.2 }}
      >
        <AnimatePresence mode="wait" initial={false}>
          {value ? (
            <motion.div
              key="on"
              initial={{ opacity: 0, rotate: -60 }}
              animate={{ opacity: 1, rotate: 0 }}
              exit={{ opacity: 0, rotate: 60 }}
              transition={{ duration: 0.3 }}
              className="flex size-5 items-center justify-center"
            >
              {iconOn}
            </motion.div>
          ) : (
            <motion.div
              key="off"
              initial={{ opacity: 0, rotate: 60 }}
              animate={{ opacity: 1, rotate: 0 }}
              exit={{ opacity: 0, rotate: -60 }}
              transition={{ duration: 0.3 }}
              className="flex size-5 items-center justify-center"
            >
              {iconOff}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </button>
  );
}
