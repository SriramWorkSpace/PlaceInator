import { parseDate } from "@internationalized/date";
import { DatePicker as ArkDatePicker } from "@ark-ui/react/date-picker";
import { Portal } from "@ark-ui/react/portal";
import { Calendar, ChevronLeft, ChevronRight, X } from "lucide-react";
import { useMemo } from "react";

import { cn } from "@/lib/utils";

/**
 * Headless date picker (Ark UI) retokenized onto this project's design
 * system rather than left with the hardcoded gray/blue Tailwind palette it
 * shipped with.
 *
 * That retokenizing is not cosmetic-only: this app's dark mode is driven by
 * a `data-theme` attribute plus a `prefers-color-scheme` fallback (see
 * styles/index.css), not Tailwind's class-based dark: strategy. Tailwind
 * v4's default `dark:` variant compiles to `@media (prefers-color-scheme)`
 * alone, so `dark:bg-gray-800`-style classes would silently ignore an
 * explicit light/dark override from the app's own theme toggle and just
 * follow the OS setting instead. Every color below is a CSS custom
 * property, which already resolves correctly under both mechanisms because
 * that's how the rest of the app's tokens work.
 *
 * The calendar grid's selected/today/outside-month states were entirely
 * unstyled in the source snippet -- Ark UI exposes them as data attributes
 * (data-selected, data-today, data-outside-range, data-disabled; present
 * when true, absent when false -- verified against
 * @zag-js/date-picker's connect.mjs rather than assumed) and this file
 * styles all of them, since a date picker with no visible selection state
 * is not functional, just decorative.
 */

const inputSurface = {
  borderColor: "var(--border)",
  background: "var(--canvas)",
  color: "var(--fg)",
};

const dayCellClassName = cn(
  "flex h-9 w-9 items-center justify-center rounded-full text-sm outline-none transition-colors",
  "hover:bg-[var(--canvas-inset)]",
  "data-[outside-range]:opacity-40",
  "data-[disabled]:pointer-events-none data-[disabled]:opacity-30",
  "data-[today]:font-semibold data-[today]:underline data-[today]:underline-offset-4",
  "data-[selected]:bg-[var(--accent)] data-[selected]:text-[var(--accent-fg)] data-[selected]:hover:bg-[var(--accent)]",
  "data-[focus]:ring-2 data-[focus]:ring-[var(--accent)] data-[focus]:ring-offset-1 data-[focus]:ring-offset-[var(--canvas-subtle)]",
);

const gridCellClassName = cn(
  "rounded-lg px-2 py-1.5 text-sm outline-none transition-colors",
  "hover:bg-[var(--canvas-inset)]",
  "data-[disabled]:pointer-events-none data-[disabled]:opacity-30",
  "data-[selected]:bg-[var(--accent)] data-[selected]:text-[var(--accent-fg)]",
);

const viewNavButtonClassName = cn(
  "icon-btn flex h-7 w-7 items-center justify-center rounded-full",
  "hover:bg-[var(--canvas-inset)]",
);

interface DatePickerFieldProps {
  label?: string;
  placeholder?: string;
  /** ISO date string ("YYYY-MM-DD"), or null when cleared. */
  value?: string | null;
  onValueChange?: (value: string | null) => void;
  disabled?: boolean;
}

/**
 * The controlled primitive real forms should use -- see Jobs.tsx's
 * deadline field for the reference integration. Wraps Ark UI's ISO-string
 * `value`/`onValueChange` API (via valueAsString / onValueChange) so
 * callers work in plain strings rather than Ark's internal date object.
 */
export function DatePickerField({
  label = "Date",
  placeholder = "Pick a date",
  value,
  onValueChange,
  disabled,
}: DatePickerFieldProps) {
  // Root wants @internationalized/date's DateValue, not a plain string --
  // parse defensively since `value` may come from user-editable state that
  // isn't guaranteed to be a valid ISO date yet.
  const parsedValue = useMemo(() => {
    if (!value) return [];
    try {
      return [parseDate(value)];
    } catch {
      return [];
    }
  }, [value]);

  return (
    <ArkDatePicker.Root
      value={parsedValue}
      onValueChange={(details) => onValueChange?.(details.valueAsString[0] ?? null)}
      disabled={disabled}
    >
      <ArkDatePicker.Label className="mb-1.5 block text-sm font-medium" style={{ color: "var(--fg)" }}>
        {label}
      </ArkDatePicker.Label>

      <ArkDatePicker.Control className="field-control flex items-center gap-1 border pl-3.5 pr-1.5 py-1">
        <ArkDatePicker.Input
          className="flex-1 bg-transparent py-1 text-sm outline-none"
          style={{ color: "var(--fg)" }}
          placeholder={placeholder}
        />
        <ArkDatePicker.ClearTrigger
          className="icon-btn flex h-7 w-7 items-center justify-center rounded-full"
          style={{ color: "var(--fg-subtle)" }}
        >
          <X size={14} />
        </ArkDatePicker.ClearTrigger>
        <ArkDatePicker.Trigger
          className="icon-btn flex h-7 w-7 items-center justify-center rounded-full"
          style={{ color: "var(--fg-muted)" }}
        >
          <Calendar size={16} />
        </ArkDatePicker.Trigger>
      </ArkDatePicker.Control>

      <Portal>
        <ArkDatePicker.Positioner>
          <CalendarPopup />
        </ArkDatePicker.Positioner>
      </Portal>
    </ArkDatePicker.Root>
  );
}

/** The floating calendar content, shared by DatePickerField and Basic. */
function CalendarPopup() {
  return (
    <ArkDatePicker.Content
      className="w-[calc(100vw-2rem)] max-w-xs border p-3"
      style={{
        borderColor: "var(--border)",
        background: "var(--canvas-subtle)",
        borderRadius: "var(--radius-panel)",
        boxShadow: "var(--shadow-popover)",
      }}
    >
      <div className="mb-3 flex gap-2">
        <ArkDatePicker.YearSelect className="field-control flex-1 border px-2 py-1.5 text-sm" style={inputSurface} />
        <ArkDatePicker.MonthSelect className="field-control flex-1 border px-2 py-1.5 text-sm" style={inputSurface} />
      </div>

      <ArkDatePicker.View view="day">
        <ArkDatePicker.Context>
          {(datePicker) => (
            <>
              <ArkDatePicker.ViewControl className="mb-2 flex items-center justify-between text-sm font-medium">
                <ArkDatePicker.PrevTrigger className={viewNavButtonClassName} style={{ color: "var(--fg-muted)" }}>
                  <ChevronLeft size={16} />
                </ArkDatePicker.PrevTrigger>
                <ArkDatePicker.ViewTrigger className="rounded-lg px-2 py-1 hover:bg-[var(--canvas-inset)]">
                  <ArkDatePicker.RangeText />
                </ArkDatePicker.ViewTrigger>
                <ArkDatePicker.NextTrigger className={viewNavButtonClassName} style={{ color: "var(--fg-muted)" }}>
                  <ChevronRight size={16} />
                </ArkDatePicker.NextTrigger>
              </ArkDatePicker.ViewControl>

              <ArkDatePicker.Table className="w-full border-collapse text-center text-sm">
                <ArkDatePicker.TableHead>
                  <ArkDatePicker.TableRow>
                    {datePicker.weekDays.map((weekDay, id) => (
                      <ArkDatePicker.TableHeader
                        key={id}
                        className="eyebrow py-1.5 font-normal"
                        style={{ color: "var(--fg-subtle)" }}
                      >
                        {weekDay.short}
                      </ArkDatePicker.TableHeader>
                    ))}
                  </ArkDatePicker.TableRow>
                </ArkDatePicker.TableHead>
                <ArkDatePicker.TableBody>
                  {datePicker.weeks.map((week, id) => (
                    <ArkDatePicker.TableRow key={id}>
                      {week.map((day, id) => (
                        <ArkDatePicker.TableCell key={id} value={day}>
                          <ArkDatePicker.TableCellTrigger className={dayCellClassName}>
                            {day.day}
                          </ArkDatePicker.TableCellTrigger>
                        </ArkDatePicker.TableCell>
                      ))}
                    </ArkDatePicker.TableRow>
                  ))}
                </ArkDatePicker.TableBody>
              </ArkDatePicker.Table>
            </>
          )}
        </ArkDatePicker.Context>
      </ArkDatePicker.View>

      <ArkDatePicker.View view="month">
        <ArkDatePicker.Context>
          {(datePicker) => (
            <>
              <ArkDatePicker.ViewControl className="mb-2 flex items-center justify-between text-sm font-medium">
                <ArkDatePicker.PrevTrigger className={viewNavButtonClassName} style={{ color: "var(--fg-muted)" }}>
                  <ChevronLeft size={16} />
                </ArkDatePicker.PrevTrigger>
                <ArkDatePicker.ViewTrigger className="rounded-lg px-2 py-1 hover:bg-[var(--canvas-inset)]">
                  <ArkDatePicker.RangeText />
                </ArkDatePicker.ViewTrigger>
                <ArkDatePicker.NextTrigger className={viewNavButtonClassName} style={{ color: "var(--fg-muted)" }}>
                  <ChevronRight size={16} />
                </ArkDatePicker.NextTrigger>
              </ArkDatePicker.ViewControl>
              <ArkDatePicker.Table className="w-full text-sm">
                <ArkDatePicker.TableBody>
                  {datePicker.getMonthsGrid({ columns: 4, format: "short" }).map((months, id) => (
                    <ArkDatePicker.TableRow key={id}>
                      {months.map((month, id) => (
                        <ArkDatePicker.TableCell key={id} value={month.value}>
                          <ArkDatePicker.TableCellTrigger className={gridCellClassName}>
                            {month.label}
                          </ArkDatePicker.TableCellTrigger>
                        </ArkDatePicker.TableCell>
                      ))}
                    </ArkDatePicker.TableRow>
                  ))}
                </ArkDatePicker.TableBody>
              </ArkDatePicker.Table>
            </>
          )}
        </ArkDatePicker.Context>
      </ArkDatePicker.View>

      <ArkDatePicker.View view="year">
        <ArkDatePicker.Context>
          {(datePicker) => (
            <>
              <ArkDatePicker.ViewControl className="mb-2 flex items-center justify-between text-sm font-medium">
                <ArkDatePicker.PrevTrigger className={viewNavButtonClassName} style={{ color: "var(--fg-muted)" }}>
                  <ChevronLeft size={16} />
                </ArkDatePicker.PrevTrigger>
                <ArkDatePicker.ViewTrigger className="rounded-lg px-2 py-1 hover:bg-[var(--canvas-inset)]">
                  <ArkDatePicker.RangeText />
                </ArkDatePicker.ViewTrigger>
                <ArkDatePicker.NextTrigger className={viewNavButtonClassName} style={{ color: "var(--fg-muted)" }}>
                  <ChevronRight size={16} />
                </ArkDatePicker.NextTrigger>
              </ArkDatePicker.ViewControl>
              <ArkDatePicker.Table className="w-full text-sm">
                <ArkDatePicker.TableBody>
                  {datePicker.getYearsGrid({ columns: 4 }).map((years, id) => (
                    <ArkDatePicker.TableRow key={id}>
                      {years.map((year, id) => (
                        <ArkDatePicker.TableCell key={id} value={year.value}>
                          <ArkDatePicker.TableCellTrigger className={gridCellClassName}>
                            {year.label}
                          </ArkDatePicker.TableCellTrigger>
                        </ArkDatePicker.TableCell>
                      ))}
                    </ArkDatePicker.TableRow>
                  ))}
                </ArkDatePicker.TableBody>
              </ArkDatePicker.Table>
            </>
          )}
        </ArkDatePicker.Context>
      </ArkDatePicker.View>
    </ArkDatePicker.Content>
  );
}

/**
 * Uncontrolled demo matching the originally supplied component 1:1 in
 * structure (kept as `Basic` for import compatibility with demo.tsx).
 * Real usage in this app goes through DatePickerField above instead, since
 * a form needs the selected value, not just a self-contained widget.
 */
export const Basic = () => {
  return (
    <div className="mx-auto w-full max-w-md p-4">
      <ArkDatePicker.Root>
        <ArkDatePicker.Label className="mb-2 block text-sm font-medium" style={{ color: "var(--fg)" }}>
          Select Date
        </ArkDatePicker.Label>

        <ArkDatePicker.Control className="field-control flex items-center gap-1 border pl-3.5 pr-1.5 py-1">
          <ArkDatePicker.Input
            className="flex-1 bg-transparent py-1 text-sm outline-none"
            style={{ color: "var(--fg)" }}
            placeholder="Pick a date"
          />
          <ArkDatePicker.Trigger
            className="icon-btn flex h-7 w-7 items-center justify-center rounded-full"
            style={{ color: "var(--fg-muted)" }}
          >
            <Calendar size={16} />
          </ArkDatePicker.Trigger>
          <ArkDatePicker.ClearTrigger
            className="icon-btn flex h-7 w-7 items-center justify-center rounded-full"
            style={{ color: "var(--danger)" }}
          >
            <X size={14} />
          </ArkDatePicker.ClearTrigger>
        </ArkDatePicker.Control>

        <Portal>
          <ArkDatePicker.Positioner>
            <CalendarPopup />
          </ArkDatePicker.Positioner>
        </Portal>
      </ArkDatePicker.Root>
    </div>
  );
};
