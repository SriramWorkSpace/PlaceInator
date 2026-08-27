import { Slider as ArkSlider } from "@ark-ui/react/slider";

import { cn } from "@/lib/utils";

/**
 * Headless slider (Ark UI) retokenized onto this project's design system,
 * same convention as date-picker.tsx and switch.tsx in this directory --
 * this app's CSS custom properties rather than a hardcoded gray/blue
 * palette. Replaces Settings.tsx's raw `<input type="range">`, the one
 * control left in the app with no custom styling at all.
 *
 * Track/range/thumb read `--border`/`--canvas-inset`/`--accent` (the same
 * trio `.field-control`'s focus treatment already uses) so it sits visually
 * next to text inputs and selects as one control family, not a foreign
 * native widget.
 */
export function Slider({
  value,
  onValueChange,
  min = 0,
  max = 100,
  step = 1,
  disabled,
  "aria-label": ariaLabel,
}: {
  value: number;
  onValueChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  "aria-label"?: string;
}) {
  return (
    <ArkSlider.Root
      value={[value]}
      onValueChange={(details) => onValueChange(details.value[0])}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      aria-label={ariaLabel ? [ariaLabel] : undefined}
    >
      <ArkSlider.Control className="relative flex h-6 items-center">
        <ArkSlider.Track
          className="h-1.5 w-full overflow-hidden rounded-full"
          style={{ background: "var(--canvas-inset)" }}
        >
          <ArkSlider.Range className="h-full rounded-full" style={{ background: "var(--accent)" }} />
        </ArkSlider.Track>
        <ArkSlider.Thumb
          index={0}
          className={cn(
            "block h-5 w-5 rounded-full border-2 outline-none transition-transform",
            "hover:scale-110 focus-visible:scale-110",
          )}
          style={{
            background: "var(--canvas)",
            borderColor: "var(--accent)",
            boxShadow: "var(--shadow-card)",
          }}
        >
          <ArkSlider.HiddenInput />
        </ArkSlider.Thumb>
      </ArkSlider.Control>
    </ArkSlider.Root>
  );
}
