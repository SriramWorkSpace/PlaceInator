import { lazy, Suspense, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { Button, ErrorText, Field, Select, TextArea } from "@/components/Form";
import { CheckIcon, CloseIcon } from "@/components/icons";
import { EmptyState, Page } from "@/components/Page";
import { listJobs, listResumes, tailorResume, tailorResumeAsPdf } from "@/lib/api";
import type { BulletOut, SectionOut, TailorIn, TailorOut } from "@/lib/types";
import { useTheme } from "@/lib/theme";

// @monaco-editor/react pulls in real weight for one route -- lazy-loaded the
// same way Jobs.tsx lazy-loads its DatePicker, rather than paid for by every
// route's initial load. Imported via @/lib/monaco-editor, not the package
// directly, so the loader is configured to use the bundled monaco-editor
// instead of fetching it from a CDN at runtime -- see that module's docstring.
const Editor = lazy(() => import("@/lib/monaco-editor"));

export function Tailor() {
  const { data: resumes } = useQuery({ queryKey: ["resumes"], queryFn: listResumes });
  const { data: jobs } = useQuery({ queryKey: ["jobs"], queryFn: listJobs });

  const primaryResume = resumes?.find((r) => r.is_primary) ?? resumes?.[0];
  const [resumeId, setResumeId] = useState<number | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);
  const [excludedBulletIds, setExcludedBulletIds] = useState<Set<number>>(new Set());

  const effectiveResumeId = resumeId ?? primaryResume?.id ?? null;

  const tailor = useMutation({
    mutationFn: tailorResume,
  });

  const runTailor = (excluded: Set<number>) => {
    if (effectiveResumeId === null || jobId === null) return;
    tailor.mutate({
      resume_id: effectiveResumeId,
      job_id: jobId,
      excluded_bullet_ids: [...excluded],
    });
  };

  const toggleBullet = (bulletId: number) => {
    const next = new Set(excludedBulletIds);
    if (next.has(bulletId)) next.delete(bulletId);
    else next.add(bulletId);
    setExcludedBulletIds(next);
    runTailor(next);
  };

  const canTailor = effectiveResumeId !== null && jobId !== null;
  const selectedJob = jobs?.find((j) => j.id === jobId);

  return (
    <Page
      title="Resume Tailoring"
      description="Restructure a LaTeX resume for a specific job description. Content is reordered, selected, and emphasized — never rewritten, and nothing is ever invented."
    >
      <form
        className="card flex flex-wrap items-end gap-3 rounded-[var(--radius-panel)] border p-6"
        style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
        onSubmit={(e) => {
          e.preventDefault();
          setExcludedBulletIds(new Set());
          runTailor(new Set());
        }}
      >
        <div className="min-w-56 flex-1">
          <Field label="Resume">
            <Select
              value={effectiveResumeId ?? ""}
              onChange={(e) => setResumeId(Number(e.target.value))}
            >
              {!resumes?.length && <option value="">No resumes yet</option>}
              {resumes?.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                  {r.is_primary ? " (primary)" : ""}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="min-w-56 flex-1">
          <Field label="Job">
            <Select value={jobId ?? ""} onChange={(e) => setJobId(Number(e.target.value))}>
              <option value="">Choose a job…</option>
              {jobs?.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.company} — {j.designation}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Button type="submit" disabled={!canTailor || tailor.isPending}>
          {tailor.isPending ? "Tailoring…" : "Tailor"}
        </Button>
      </form>

      {tailor.isError && (
        <div className="mt-3">
          <ErrorText onDismiss={() => tailor.reset()}>{(tailor.error as Error).message}</ErrorText>
        </div>
      )}

      {!tailor.data && !tailor.isPending && (
        <div className="mt-6">
          <EmptyState
            title="Nothing to tailor yet"
            hint="Pick a resume from your library and a job, then tailor. Sources that can't be reordered further (custom bullet macros, missing sections) still round-trip safely — they just move as a whole block."
          />
        </div>
      )}

      {tailor.data && effectiveResumeId !== null && jobId !== null && (
        <TailorResult
          result={tailor.data}
          jobLabel={selectedJob ? `${selectedJob.company} — ${selectedJob.designation}` : ""}
          onToggleBullet={toggleBullet}
          tailorInput={{
            resume_id: effectiveResumeId,
            job_id: jobId,
            excluded_bullet_ids: [...excludedBulletIds],
          }}
        />
      )}
    </Page>
  );
}

function TailorResult({
  result,
  jobLabel,
  onToggleBullet,
  tailorInput,
}: {
  result: TailorOut;
  jobLabel: string;
  onToggleBullet: (bulletId: number) => void;
  tailorInput: TailorIn;
}) {
  const { theme } = useTheme();

  const download = () => {
    const blob = new Blob([result.tex], { type: "text/x-tex" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "tailored_resume.tex";
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadPdf = useMutation({
    mutationFn: () => tailorResumeAsPdf(tailorInput),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "tailored_resume.pdf";
      a.click();
      URL.revokeObjectURL(url);
    },
  });

  return (
    <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
      <div className="space-y-6">
        <RequirementCoverage
          jobLabel={jobLabel}
          matched={result.requirements_matched}
          missing={result.requirements_missing}
        />
        <ChangeLog sections={result.sections} onToggleBullet={onToggleBullet} />
      </div>

      <div
        className="card overflow-hidden rounded-[var(--radius-panel)] border"
        style={{ borderColor: "var(--border)" }}
      >
        <div
          className="flex items-center justify-between border-b px-4 py-2.5"
          style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
        >
          <span className="text-sm font-medium">Tailored_Resume.tex</span>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => downloadPdf.mutate()}
              disabled={downloadPdf.isPending}
              title="First PDF on a fresh install can take a few minutes while the PDF engine sets itself up; every one after that is fast."
            >
              {downloadPdf.isPending ? "Compiling…" : "Download PDF"}
            </Button>
            <Button type="button" variant="secondary" onClick={download}>
              Download .tex
            </Button>
          </div>
        </div>
        {downloadPdf.isError && (
          <div className="border-b px-4 py-2.5" style={{ borderColor: "var(--border)" }}>
            <ErrorText onDismiss={() => downloadPdf.reset()}>
              {(downloadPdf.error as Error).message}
            </ErrorText>
          </div>
        )}
        <Suspense fallback={<TexPreviewFallback text={result.tex} />}>
          <Editor
            height="600px"
            language="latex"
            value={result.tex}
            theme={theme === "dark" ? "vs-dark" : "light"}
            options={{ readOnly: true, minimap: { enabled: false }, fontSize: 13 }}
          />
        </Suspense>
      </div>
    </div>
  );
}

/** Plain-text fallback shown while the Monaco chunk loads -- avoids a blank
 * panel and any layout shift once it's ready, the same reasoning as Jobs.tsx's
 * DatePickerFieldSkeleton. */
function TexPreviewFallback({ text }: { text: string }) {
  return (
    <TextArea
      readOnly
      value={text}
      rows={28}
      className="rounded-none border-0"
      style={{ resize: "none" }}
    />
  );
}

function RequirementCoverage({
  jobLabel,
  matched,
  missing,
}: {
  jobLabel: string;
  matched: string[];
  missing: string[];
}) {
  const total = matched.length + missing.length;
  const coveragePercent = total === 0 ? 0 : Math.round((matched.length / total) * 100);

  return (
    <div
      className="card rounded-[var(--radius-panel)] border p-5"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium">{jobLabel}</p>
        {total > 0 && (
          <span className="text-xs font-semibold" style={{ color: "var(--section-tailor)" }}>
            {coveragePercent}% covered
          </span>
        )}
      </div>
      {total > 0 && (
        <div
          className="mt-2.5 h-1.5 overflow-hidden rounded-full"
          style={{ background: "var(--canvas-inset)" }}
          role="img"
          aria-label={`${coveragePercent}% of requirements covered`}
        >
          <div
            className="h-full rounded-full"
            style={{ width: `${coveragePercent}%`, background: "var(--section-tailor)" }}
          />
        </div>
      )}
      <div className="mt-3 space-y-2">
        {matched.map((id) => (
          <p key={id} className="flex items-center gap-1.5 text-xs" style={{ color: "var(--success)" }}>
            <CheckIcon width={13} height={13} />
            {id}
          </p>
        ))}
        {missing.map((id) => (
          <p key={id} className="flex items-center gap-1.5 text-xs" style={{ color: "var(--fg-subtle)" }}>
            <CloseIcon width={13} height={13} />
            {id}
          </p>
        ))}
        {missing.length > 0 && (
          <p className="mt-2 text-xs" style={{ color: "var(--fg-subtle)" }}>
            Reason: not present in the supplied resume.
          </p>
        )}
      </div>
    </div>
  );
}

function ChangeLog({
  sections,
  onToggleBullet,
}: {
  sections: SectionOut[];
  onToggleBullet: (bulletId: number) => void;
}) {
  const ordered = [...sections].sort((a, b) => a.new_index - b.new_index);

  return (
    <div
      className="card rounded-[var(--radius-panel)] border p-5"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <p className="text-sm font-medium">Changes</p>
      <ul className="mt-3 space-y-4">
        {ordered.map((section) => (
          <li key={section.heading}>
            <p className="text-xs font-medium">
              {section.heading}
              {section.original_index !== section.new_index && (
                <span
                  className="ml-1.5 inline-flex items-center gap-1"
                  style={{ color: "var(--success)" }}
                >
                  <CheckIcon width={11} height={11} />
                  moved
                </span>
              )}
            </p>
            {section.bullets.length > 0 && (
              <ul className="mt-1.5 space-y-1.5">
                {[...section.bullets]
                  .sort((a, b) => a.new_index - b.new_index)
                  .map((bullet) => (
                    <BulletRow key={bullet.bullet_id} bullet={bullet} onToggle={onToggleBullet} />
                  ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function BulletRow({
  bullet,
  onToggle,
}: {
  bullet: BulletOut;
  onToggle: (bulletId: number) => void;
}) {
  return (
    <li className="flex items-start gap-2 text-xs" style={{ color: "var(--fg-muted)" }}>
      <input
        type="checkbox"
        checked={!bullet.excluded}
        onChange={() => onToggle(bullet.bullet_id)}
        className="mt-0.5 shrink-0"
        aria-label={bullet.excluded ? "Include this bullet" : "Exclude this bullet"}
      />
      <span
        className={bullet.excluded ? "line-through opacity-50" : ""}
        style={
          bullet.suggested_removal && !bullet.excluded ? { color: "var(--fg-subtle)" } : undefined
        }
      >
        {bullet.text}
        {bullet.suggested_removal && !bullet.excluded && (
          <span className="ml-1.5" style={{ color: "var(--fg-subtle)" }}>
            (low relevance — suggested for removal)
          </span>
        )}
      </span>
    </li>
  );
}
