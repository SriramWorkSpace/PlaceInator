/** Splits/composes a full name into first/middle/last parts for the
 * Profile/Onboarding forms' three-field name entry. The backend still
 * stores one `full_name` string (used everywhere -- placement-sheet
 * matching, display, resume autofill), so this is purely a frontend
 * decomposition for entry, not a schema change: first word is the first
 * name, last word is the last name, anything between is the middle name.
 * Imperfect for names that don't fit that shape, but matches exactly the
 * three fields requested and is the same heuristic most Western-style forms
 * use for splitting an existing full name back into parts for editing. */
export interface NameParts {
  first: string;
  middle: string;
  last: string;
}

export const EMPTY_NAME_PARTS: NameParts = { first: "", middle: "", last: "" };

export function splitFullName(fullName: string): NameParts {
  const words = fullName.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return { ...EMPTY_NAME_PARTS };
  if (words.length === 1) return { first: words[0], middle: "", last: "" };
  if (words.length === 2) return { first: words[0], middle: "", last: words[1] };
  return { first: words[0], middle: words.slice(1, -1).join(" "), last: words[words.length - 1] };
}

export function composeFullName(parts: NameParts): string {
  return [parts.first, parts.middle, parts.last]
    .map((s) => s.trim())
    .filter(Boolean)
    .join(" ");
}

export function isEmptyName(parts: NameParts): boolean {
  return !parts.first.trim() && !parts.middle.trim() && !parts.last.trim();
}
