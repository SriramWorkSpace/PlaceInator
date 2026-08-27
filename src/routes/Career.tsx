import { useQuery } from "@tanstack/react-query";

import { EmptyState, Page, SectionCard } from "@/components/Page";
import { listSkillGaps, NotOnboardedError } from "@/lib/api";
import type { SkillGapOut } from "@/lib/types";

export function Career() {
  const { data: gaps, isPending, error } = useQuery({
    queryKey: ["career", "skill-gaps"],
    queryFn: listSkillGaps,
    retry: (count, err) => !(err instanceof NotOnboardedError) && count < 2,
  });

  const notOnboarded = error instanceof NotOnboardedError;

  // Already sorted by priority (placeinator/career/gaps.py); split into
  // required-somewhere vs preferred-only rather than one flat list, so a
  // skill blocking an application reads differently from one that would
  // just help.
  const required = gaps?.filter((g) => g.evidence.some((e) => e.required)) ?? [];
  const preferred = gaps?.filter((g) => !g.evidence.some((e) => e.required)) ?? [];
  const maxPriority = gaps && gaps.length > 0 ? gaps[0].priority : 1;

  return (
    <Page title="Skill Intelligence" description="Skill gaps between your profile and your target roles.">
      {notOnboarded && (
        <EmptyState
          title="Complete your profile first"
          hint="Skill gaps are computed from your ranked target jobs. Onboard and add at least one job to see them."
        />
      )}
      {!notOnboarded && !isPending && (!gaps || gaps.length === 0) && (
        <EmptyState
          title="Not enough data yet"
          hint="Add resumes and target jobs first. Gaps are ranked by how often a skill appears across the roles you are aiming for, weighted by how well each role matches you."
        />
      )}
      {required.length > 0 && (
        <SectionCard
          eyebrow="Blocking"
          eyebrowColor="var(--danger)"
          title="Required somewhere"
          description="At least one target job requires these outright."
        >
          <ul className="space-y-3">
            {required.map((gap) => (
              <SkillGapRow key={gap.skill_id} gap={gap} maxPriority={maxPriority} />
            ))}
          </ul>
        </SectionCard>
      )}
      {preferred.length > 0 && (
        <div className={required.length > 0 ? "mt-6" : undefined}>
          <SectionCard
            eyebrow="Would help"
            eyebrowColor="var(--section-career)"
            title="Preferred, not required"
            description="Never blocking, but shows up as a nice-to-have across your target roles."
          >
            <ul className="space-y-3">
              {preferred.map((gap) => (
                <SkillGapRow key={gap.skill_id} gap={gap} maxPriority={maxPriority} />
              ))}
            </ul>
          </SectionCard>
        </div>
      )}
    </Page>
  );
}

function SkillGapRow({ gap, maxPriority }: { gap: SkillGapOut; maxPriority: number }) {
  const displayName = gap.skill_id.replace(/-/g, " ");
  const requiredCount = gap.evidence.filter((e) => e.required).length;
  // priority is a sum of overall_score across matching jobs (unbounded), not
  // a 0-1 fraction -- normalized against this list's own max so the bar is a
  // relative "how much this one matters next to the others", the only scale
  // that's actually meaningful here.
  const widthPercent = Math.max(4, Math.round((gap.priority / maxPriority) * 100));

  return (
    <li
      className="card-hover rounded-[var(--radius-input)] border p-4"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
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
          <div
            className="mt-2.5 h-1.5 overflow-hidden rounded-full"
            style={{ background: "var(--canvas-inset)" }}
            role="img"
            aria-label={`Priority: ${widthPercent}% relative to your highest-priority gap`}
          >
            <div
              className="h-full rounded-full"
              style={{ width: `${widthPercent}%`, background: "var(--section-career)" }}
            />
          </div>
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
