import { useQuery } from "@tanstack/react-query";

import { EmptyState, Page } from "@/components/Page";
import { listSkillGaps, NotOnboardedError } from "@/lib/api";
import type { SkillGapOut } from "@/lib/types";

export function Career() {
  const { data: gaps, isPending, error } = useQuery({
    queryKey: ["career", "skill-gaps"],
    queryFn: listSkillGaps,
    retry: (count, err) => !(err instanceof NotOnboardedError) && count < 2,
  });

  const notOnboarded = error instanceof NotOnboardedError;

  return (
    <Page title="Skill Intelligence" description="Skill gaps between your profile and your target roles.">
      {notOnboarded && (
        <EmptyState
          title="Complete your profile first"
          hint="Skill gaps are computed from your ranked target jobs -- onboard and add at least one job to see them."
        />
      )}
      {!notOnboarded && !isPending && (!gaps || gaps.length === 0) && (
        <EmptyState
          title="Not enough data yet"
          hint="Add resumes and target jobs first. Gaps are ranked by how often a skill appears across the roles you are aiming for, weighted by how well each role matches you."
        />
      )}
      {gaps && gaps.length > 0 && (
        <ul className="space-y-3">
          {gaps.map((gap) => (
            <SkillGapRow key={gap.skill_id} gap={gap} />
          ))}
        </ul>
      )}
    </Page>
  );
}

function SkillGapRow({ gap }: { gap: SkillGapOut }) {
  const displayName = gap.skill_id.replace(/-/g, " ");
  const requiredCount = gap.evidence.filter((e) => e.required).length;

  return (
    <li
      className="card-hover rounded-[var(--radius-input)] border p-4"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium capitalize">{displayName}</p>
          <p className="mt-1 text-xs" style={{ color: "var(--fg-subtle)" }}>
            Missing from {gap.evidence.length} target job{gap.evidence.length === 1 ? "" : "s"}
            {requiredCount > 0 && ` (required in ${requiredCount})`} —{" "}
            {gap.evidence
              .slice(0, 3)
              .map((e) => `${e.designation} at ${e.company}`)
              .join(", ")}
            {gap.evidence.length > 3 && ", …"}
          </p>
        </div>
        {gap.resource && (
          <a
            href={gap.resource.url}
            target="_blank"
            rel="noreferrer noopener"
            className="shrink-0 whitespace-nowrap text-xs underline underline-offset-2"
            style={{ color: "var(--accent)" }}
          >
            {gap.resource.title} ↗
          </a>
        )}
      </div>
    </li>
  );
}
