import { createListCollection, Select as ArkSelect } from "@ark-ui/react/select";
import { Portal } from "@ark-ui/react/portal";
import { Check, ChevronDown } from "lucide-react";
import { Children, isValidElement, type ReactElement, type ReactNode, useMemo } from "react";

/**
 * Themed replacement for a plain native `<select>` -- the browser's own
 * dropdown popup can't be restyled with CSS (only the closed control can),
 * so every select in the app opened as an unthemed OS menu no matter what
 * the trigger looked like. Ark UI's headless Select (same library already
 * used for date-picker.tsx/switch.tsx/slider.tsx) renders its own popup
 * content, so the open state gets this app's tokens too.
 *
 * Deliberately a drop-in replacement for the native-`<select>`-shaped API
 * every call site across the app already uses --
 * `<Select value={x} onChange={(e) => ...e.target.value...}>` with
 * `<option value="...">Label</option>` children -- rather than Ark's own
 * `items`/`collection` props. That existing API is parsed from `children`
 * into a collection internally, so no route file needed to change to pick
 * up the theming.
 */
export function Select({
  value: rawValue,
  onChange,
  disabled,
  children,
}: {
  // Matches native <select>'s own value prop ergonomics -- several call
  // sites across the app pass a numeric id (`value={resumeId ?? ""}`),
  // which a real <select> coerces fine but a strict `string` prop wouldn't.
  value: string | number;
  onChange: (event: { target: { value: string } }) => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  const value = String(rawValue);
  const items = useMemo(() => {
    return Children.toArray(children)
      .filter((child): child is ReactElement<{ value: string; children?: ReactNode }> =>
        isValidElement(child),
      )
      .map((child) => ({
        value: String(child.props.value),
        label: typeof child.props.children === "string" ? child.props.children : String(child.props.value),
      }));
  }, [children]);

  const collection = useMemo(
    () =>
      createListCollection({
        items,
        itemToValue: (item) => item.value,
        itemToString: (item) => item.label,
      }),
    [items],
  );

  const selectedLabel = items.find((item) => item.value === value)?.label ?? "";

  return (
    <ArkSelect.Root
      collection={collection}
      value={value === "" && !items.some((i) => i.value === "") ? [] : [value]}
      onValueChange={(details) => onChange({ target: { value: details.value[0] ?? "" } })}
      disabled={disabled}
    >
      <ArkSelect.Control>
        <ArkSelect.Trigger
          className="field-control flex w-full items-center justify-between gap-2 border px-3.5 py-2.5 text-left text-sm outline-none"
          style={{ borderColor: "var(--border)", background: "var(--canvas)", color: "var(--fg)" }}
        >
          <span className="truncate">{selectedLabel}</span>
          <ChevronDown size={15} style={{ color: "var(--fg-subtle)" }} />
        </ArkSelect.Trigger>
      </ArkSelect.Control>

      <Portal>
        <ArkSelect.Positioner>
          <ArkSelect.Content
            className="max-h-64 overflow-y-auto border p-1"
            style={{
              borderColor: "var(--border)",
              background: "var(--canvas-subtle)",
              borderRadius: "var(--radius-input)",
              boxShadow: "var(--shadow-popover)",
              minWidth: "var(--reference-width)",
            }}
          >
            {collection.items.map((item) => (
              <ArkSelect.Item
                key={item.value}
                item={item}
                className="flex cursor-pointer items-center justify-between gap-2 rounded-[calc(var(--radius-input)-4px)] px-3 py-2 text-sm outline-none data-[highlighted]:bg-[var(--canvas-inset)]"
              >
                <ArkSelect.ItemText>{item.label}</ArkSelect.ItemText>
                <ArkSelect.ItemIndicator>
                  <Check size={14} style={{ color: "var(--accent)" }} />
                </ArkSelect.ItemIndicator>
              </ArkSelect.Item>
            ))}
          </ArkSelect.Content>
        </ArkSelect.Positioner>
      </Portal>

      <ArkSelect.HiddenSelect />
    </ArkSelect.Root>
  );
}
