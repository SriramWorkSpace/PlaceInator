import { Field, TextInput } from "@/components/Form";
import type { NameParts } from "@/lib/name";

/**
 * First / Middle (optional) / Last -- a fully controlled, stateless
 * presentational component. The caller owns `parts` as its own state and
 * passes `onChange`; this never holds or derives its own copy, which is
 * exactly what the old single "Target roles" text field got wrong
 * (re-deriving a displayed value from parsed state on every keystroke
 * silently ate a just-typed space). Each of the three inputs here is its
 * own independent piece of state with nothing round-tripped through it, so
 * that class of bug can't happen here.
 *
 * Labels are kept to a single line on purpose -- "Middle name (optional)"
 * used to wrap onto two lines while "First name"/"Last name" stayed on one,
 * which threw the three inputs out of alignment in the grid row below.
 * Optionality is conveyed by the placeholder instead.
 */
export function NameFields({
  parts,
  onChange,
}: {
  parts: NameParts;
  onChange: (parts: NameParts) => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-3">
      <Field label="First name">
        <TextInput
          required
          placeholder="First name"
          value={parts.first}
          onChange={(e) => onChange({ ...parts, first: e.target.value })}
        />
      </Field>
      <Field label="Middle name">
        <TextInput
          placeholder="Optional"
          value={parts.middle}
          onChange={(e) => onChange({ ...parts, middle: e.target.value })}
        />
      </Field>
      <Field label="Last name">
        <TextInput
          required
          placeholder="Last name"
          value={parts.last}
          onChange={(e) => onChange({ ...parts, last: e.target.value })}
        />
      </Field>
    </div>
  );
}
