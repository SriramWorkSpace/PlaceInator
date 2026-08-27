import { TagsInput } from "@ark-ui/react/tags-input";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { CloseIcon } from "@/components/icons";
import { listJobs } from "@/lib/api";

/**
 * Multi-role picker (Profile & Onboarding's "Target roles"), replacing a
 * plain comma-separated TextInput that had a real bug: its value was
 * `target_roles.join(", ")`, re-derived by splitting on every keystroke via
 * `.split(",").map(s => s.trim())`. Typing a space mid-role got trimmed
 * back out on the very next render -- a space could never actually land,
 * so multi-word roles like "Backend Engineer" were impossible to type
 * continuously. Ark UI's TagsInput keeps the in-progress typed text
 * (`inputValue`) and the committed list (`value: string[]`) as genuinely
 * separate state, which removes the bug structurally rather than patching
 * around it.
 *
 * Suggestions come from two real sources, never a fabricated one: a static
 * baseline of common tech-job titles, plus every distinct `designation`
 * already seen among the jobs this profile has added -- same "never invent,
 * prefer real data" principle ADR 0002 applies everywhere else in this app.
 */
const COMMON_ROLES = [
  "Software Engineer",
  "Backend Engineer",
  "Frontend Engineer",
  "Full Stack Engineer",
  "SDE",
  "SDE 1",
  "SDE 2",
  "Data Scientist",
  "Data Analyst",
  "Data Engineer",
  "Machine Learning Engineer",
  "DevOps Engineer",
  "Site Reliability Engineer",
  "Cloud Engineer",
  "Mobile Engineer",
  "Android Developer",
  "iOS Developer",
  "QA Engineer",
  "Test Engineer",
  "Product Manager",
  "Business Analyst",
  "UI/UX Designer",
  "Security Engineer",
  "Embedded Systems Engineer",
];

export function RolePicker({
  value,
  onValueChange,
}: {
  value: string[];
  onValueChange: (value: string[]) => void;
}) {
  const [inputValue, setInputValue] = useState("");

  const { data: jobs } = useQuery({ queryKey: ["jobs"], queryFn: listJobs });
  const allSuggestions = useMemo(() => {
    const fromJobs = jobs?.map((j) => j.designation) ?? [];
    return Array.from(new Set([...fromJobs, ...COMMON_ROLES]));
  }, [jobs]);

  const suggestions = useMemo(() => {
    const query = inputValue.trim().toLowerCase();
    if (!query) return [];
    return allSuggestions
      .filter((role) => role.toLowerCase().includes(query) && !value.includes(role))
      .slice(0, 8);
  }, [inputValue, allSuggestions, value]);

  return (
    <TagsInput.Root
      value={value}
      onValueChange={(details) => onValueChange(details.value)}
      inputValue={inputValue}
      onInputValueChange={(details) => setInputValue(details.inputValue)}
      className="relative"
    >
      <TagsInput.Control
        className="field-control flex min-h-12 w-full flex-wrap items-center gap-1.5 border px-2.5 py-1.5"
        style={{ borderColor: "var(--border)", background: "var(--canvas)" }}
      >
        {value.map((role, index) => (
          <TagsInput.Item
            key={role}
            index={index}
            value={role}
            className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] py-1 pr-1.5 pl-2.5 text-xs font-medium"
            style={{ background: "var(--accent-subtle)", color: "var(--accent)" }}
          >
            <TagsInput.ItemPreview className="inline-flex items-center gap-1">
              <TagsInput.ItemText>{role}</TagsInput.ItemText>
              <TagsInput.ItemDeleteTrigger
                aria-label={`Remove ${role}`}
                className="flex h-4 w-4 items-center justify-center opacity-70 hover:opacity-100"
              >
                <CloseIcon width={10} height={10} />
              </TagsInput.ItemDeleteTrigger>
            </TagsInput.ItemPreview>
          </TagsInput.Item>
        ))}
        <TagsInput.Input
          placeholder={value.length === 0 ? "e.g. Backend Engineer" : "Add another…"}
          className="min-w-32 flex-1 border-none bg-transparent py-1 text-sm outline-none"
        />
      </TagsInput.Control>

      {suggestions.length > 0 && (
        <div
          className="absolute top-full right-0 left-0 z-10 mt-1.5 overflow-hidden rounded-[var(--radius-input)] border"
          style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)", boxShadow: "var(--shadow-popover)" }}
        >
          {suggestions.map((role) => (
            <button
              key={role}
              type="button"
              className="block w-full px-3.5 py-2 text-left text-sm transition-colors hover:bg-[var(--canvas-inset)]"
              // mousedown, not click/onClick: fires before the text input's
              // blur handler, so selecting a suggestion doesn't lose focus
              // (and the pending click) to the blur closing things first.
              onMouseDown={(e) => {
                e.preventDefault();
                onValueChange([...value, role]);
                setInputValue("");
              }}
            >
              {role}
            </button>
          ))}
        </div>
      )}
    </TagsInput.Root>
  );
}
