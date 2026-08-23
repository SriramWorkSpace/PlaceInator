import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button, ErrorText, Field, Select } from "@/components/Form";
import { EmptyState, Page, SectionCard } from "@/components/Page";
import {
  createOutreachDraft,
  deleteOutreachDraft,
  listOutreachDrafts,
  listOutreachTargets,
  listResumes,
  NotOnboardedError,
} from "@/lib/api";
import type { OutreachDraftOut, OutreachTargetOut } from "@/lib/types";

export function Outreach() {
  const { data: resumes } = useQuery({ queryKey: ["resumes"], queryFn: listResumes });
  const [selectedResumeId, setSelectedResumeId] = useState<number | null>(null);
  // Defaults to the primary resume once resumes load, without an effect --
  // this is derived state, computed fresh each render, not something to
  // synchronize. A real user selection (onChange below) always wins once made.
  const resumeId =
    selectedResumeId ?? (resumes && resumes.length > 0
      ? (resumes.find((r) => r.is_primary) ?? resumes[0]).id
      : null);

  const {
    data: targets,
    isPending: targetsPending,
    error: targetsError,
  } = useQuery({
    queryKey: ["outreach", "targets"],
    queryFn: listOutreachTargets,
    retry: (count, err) => !(err instanceof NotOnboardedError) && count < 2,
  });
  const { data: drafts } = useQuery({ queryKey: ["outreach", "drafts"], queryFn: listOutreachDrafts });

  const notOnboarded = targetsError instanceof NotOnboardedError;

  if (notOnboarded) {
    return (
      <Page title="Cold Outreach" description="Personalized cold-mail drafts.">
        <EmptyState
          title="Complete your profile first"
          hint="Targets are drawn from your ranked jobs -- onboard and add at least one job first."
        />
      </Page>
    );
  }

  if (!resumes || resumes.length === 0) {
    return (
      <Page title="Cold Outreach" description="Personalized cold-mail drafts.">
        <EmptyState
          title="Add a resume first"
          hint="Drafts are built from your profile and a real resume's matched content."
        />
      </Page>
    );
  }

  const draftsByJobResume = new Map((drafts ?? []).map((d) => [`${d.job_id}:${d.resume_id}`, d]));

  return (
    <Page title="Cold Outreach" description="Personalized cold-mail drafts.">
      <div className="w-60">
        <Field label="Draft using resume">
          <Select
            value={resumeId ?? ""}
            onChange={(e) => setSelectedResumeId(Number(e.target.value))}
          >
            {resumes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
                {r.is_primary ? " (primary)" : ""}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {!targetsPending && (!targets || targets.length === 0) && (
        <div className="mt-6">
          <EmptyState
            title="No targets yet"
            hint="Add and rank some jobs first -- targets are your best-matched, non-excluded opportunities."
          />
        </div>
      )}

      {targets && targets.length > 0 && resumeId !== null && (
        <ul className="mt-6 space-y-3">
          {targets.map((target) => (
            <TargetRow
              key={target.job.id}
              target={target}
              resumeId={resumeId}
              existingDraft={draftsByJobResume.get(`${target.job.id}:${resumeId}`)}
            />
          ))}
        </ul>
      )}
    </Page>
  );
}

function TargetRow({
  target,
  resumeId,
  existingDraft,
}: {
  target: OutreachTargetOut;
  resumeId: number;
  existingDraft: OutreachDraftOut | undefined;
}) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);

  const draft = useMutation({
    mutationFn: createOutreachDraft,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["outreach", "drafts"] });
      setExpanded(true);
    },
  });

  return (
    <li
      className="rounded-[var(--radius-input)] border"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <div className="flex items-center justify-between gap-4 px-4 py-3">
        <span>
          <span className="text-sm font-medium">{target.job.designation}</span>
          <span className="ml-2 text-sm" style={{ color: "var(--fg-muted)" }}>
            {target.job.company}
            {target.job.location ? ` · ${target.job.location}` : ""}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span
            className="rounded-[var(--radius-pill)] px-2.5 py-0.5 text-xs font-medium"
            style={{ background: "var(--accent-subtle)", color: "var(--accent)" }}
          >
            {Math.round(target.overall_score * 100)}% match
          </span>
          {existingDraft ? (
            <Button variant="secondary" onClick={() => setExpanded((v) => !v)}>
              {expanded ? "Hide draft" : "View draft"}
            </Button>
          ) : (
            <Button
              variant="primary"
              disabled={draft.isPending}
              onClick={() => draft.mutate({ resume_id: resumeId, job_id: target.job.id })}
            >
              {draft.isPending ? "Drafting…" : "Draft"}
            </Button>
          )}
        </span>
      </div>

      {draft.isError && (
        <div className="px-4 pb-3">
          <ErrorText onDismiss={() => draft.reset()}>{(draft.error as Error).message}</ErrorText>
        </div>
      )}

      {expanded && existingDraft && <DraftView draft={existingDraft} />}
    </li>
  );
}

function DraftView({ draft }: { draft: OutreachDraftOut }) {
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState(false);

  const remove = useMutation({
    mutationFn: deleteOutreachDraft,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["outreach", "drafts"] }),
  });

  const copyText = `Subject: ${draft.subject}\n\n${draft.body}`;

  return (
    <div className="px-4 pb-4">
      <SectionCard eyebrow="Draft" title={draft.subject}>
        <pre
          className="whitespace-pre-wrap rounded-[var(--radius-input)] border p-3 text-sm"
          style={{ borderColor: "var(--border)", background: "var(--canvas)", fontFamily: "inherit" }}
        >
          {draft.body}
        </pre>
        {/* No send action anywhere in this view, by design (spec line 423):
            the user copies this out and sends it themselves. */}
        <div className="mt-3 flex items-center gap-3">
          <Button
            variant="secondary"
            onClick={() => {
              void navigator.clipboard.writeText(copyText);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 2000);
            }}
          >
            {copied ? "Copied" : "Copy to clipboard"}
          </Button>
          <Button variant="secondary" disabled={remove.isPending} onClick={() => remove.mutate(draft.id)}>
            Delete draft
          </Button>
        </div>
      </SectionCard>
    </div>
  );
}
