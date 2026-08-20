import { lazy, Suspense, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button, ErrorText, Field, Select, TextArea, TextInput } from "@/components/Form";
import { EmptyState, Page } from "@/components/Page";
import { Table, TableCell, TableHead, TableRow } from "@/components/Table";
import {
  createManualJob,
  extractJobFromFile,
  listJobs,
  listRankedJobs,
  NotOnboardedError,
  rankResumesForJob,
  searchJobs,
} from "@/lib/api";
import {
  JD_SOURCE_FORMATS,
  JOB_SEARCH_SOURCES,
  type JdSourceFormat,
  type JobRanking,
  type JobSearchSource,
  type MatchOut,
} from "@/lib/types";

// Ark UI + @internationalized/date pull in real weight (~180KB raw) for one
// field on one route -- lazy-loaded the same way Monaco is lazy-loaded on
// Tailor only, rather than paid for by every route's initial load.
const DatePickerField = lazy(() =>
  import("@/components/ui/date-picker").then((m) => ({ default: m.DatePickerField })),
);

const EMPTY_JOB = {
  company: "",
  designation: "",
  location: "",
  description: "",
  deadline: null as string | null,
};

const JD_FORMAT_BY_EXTENSION: Record<string, JdSourceFormat> = {
  pdf: "pdf",
  docx: "docx",
};

/** Normalizes the two possible list sources into one shape so the rest of
 * the component never branches on whether ranking was available. Before
 * onboarding, GET /api/jobs/ranked 412s (ranking against preferences that
 * don't exist yet is meaningless) -- falls back to the flat list with a
 * neutral placeholder score rather than an error state, since adding a job
 * has never required a profile. */
async function loadJobs(): Promise<{ rankings: JobRanking[]; ranked: boolean }> {
  try {
    return { rankings: await listRankedJobs(), ranked: true };
  } catch (err) {
    if (!(err instanceof NotOnboardedError)) throw err;
    const jobs = await listJobs();
    return {
      ranked: false,
      rankings: jobs.map((job) => ({
        job,
        semantic_score: null,
        soft_preference_score: 0.5,
        soft_preference_reasons: [],
        overall_score: 0.5,
      })),
    };
  }
}

/**
 * Keyword/location search against indeed/linkedin/naukri (ADR 0003).
 * `blocked_reason` is a first-class, expected outcome -- not an error -- for
 * linkedin/naukri especially, so it's shown as a plain hint pointing at the
 * manual-paste form below, never as an ErrorText.
 */
function JobBoardSearch() {
  const queryClient = useQueryClient();
  const [source, setSource] = useState<JobSearchSource>("indeed");
  const [keywords, setKeywords] = useState("");
  const [location, setLocation] = useState("");

  const search = useMutation({
    mutationFn: searchJobs,
    onSuccess: (result) => {
      if (result.jobs.length > 0) {
        queryClient.invalidateQueries({ queryKey: ["jobs", "ranked"] });
      }
    },
  });

  return (
    <div
      className="card rounded-[var(--radius-panel)] border p-6"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          search.mutate({ source, keywords, location: location || undefined });
        }}
      >
        <div className="w-32">
          <Field label="Job board">
            <Select value={source} onChange={(e) => setSource(e.target.value as JobSearchSource)}>
              {JOB_SEARCH_SOURCES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="min-w-48 flex-1">
          <Field label="Keywords">
            <TextInput
              required
              placeholder="Backend Engineer"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
            />
          </Field>
        </div>
        <div className="w-44">
          <Field label="Location">
            <TextInput
              placeholder="Remote"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </Field>
        </div>
        <Button type="submit" disabled={search.isPending}>
          {search.isPending ? "Searching…" : "Search"}
        </Button>
      </form>

      {search.isError && (
        <div className="mt-3">
          <ErrorText onDismiss={() => search.reset()}>
            {(search.error as Error).message}
          </ErrorText>
        </div>
      )}

      {search.isSuccess && search.data.blocked_reason && (
        <p className="mt-3 text-xs" style={{ color: "var(--fg-subtle)" }}>
          {source} couldn't be reached ({search.data.blocked_reason}). Paste the job description
          below instead.
        </p>
      )}

      {search.isSuccess && !search.data.blocked_reason && (
        <p className="mt-3 text-xs" style={{ color: "var(--fg-subtle)" }}>
          Found {search.data.jobs.length} job{search.data.jobs.length === 1 ? "" : "s"}.
        </p>
      )}
    </div>
  );
}

export function Jobs() {
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({ queryKey: ["jobs", "ranked"], queryFn: loadJobs });
  const jobs = data?.rankings;
  const [form, setForm] = useState(EMPTY_JOB);
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);

  const [jdFormat, setJdFormat] = useState<JdSourceFormat>("pdf");
  const jdFileInput = useRef<HTMLInputElement>(null);

  const extractJd = useMutation({
    mutationFn: extractJobFromFile,
    onSuccess: (fields) => {
      // Only fill fields the user hasn't already typed something into --
      // autofill should never clobber a manual edit.
      setForm((f) => ({
        ...f,
        designation: f.designation || fields.designation || "",
        company: f.company || fields.company || "",
        description: f.description || fields.description,
      }));
    },
  });

  const addJob = useMutation({
    mutationFn: createManualJob,
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ["jobs", "ranked"] });
      setForm(EMPTY_JOB);
      extractJd.reset();
      if (jdFileInput.current) jdFileInput.current.value = "";
      setExpandedJobId(job.id);
    },
  });

  return (
    <Page
      title="Job Intelligence"
      description="Search a job board, paste a job description, or upload a JD file, to match it against your resume library (spec §2)."
    >
      <JobBoardSearch />

      <form
        className="card mt-6 space-y-3 rounded-[var(--radius-panel)] border p-6"
        style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
        onSubmit={(e) => {
          e.preventDefault();
          addJob.mutate({
            company: form.company,
            designation: form.designation,
            description: form.description,
            location: form.location || null,
            url: null,
            deadline: form.deadline,
          });
        }}
      >
        <div
          className="card rounded-[var(--radius-panel)] border p-4"
          style={{ borderColor: "var(--border)", background: "var(--canvas)" }}
        >
          <Field
            label="Upload a JD file (optional)"
            hint="Prefills the fields below from a PDF or DOCX job description. Anything you've already typed is left alone."
          >
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-48 flex-1">
                <input
                  ref={jdFileInput}
                  type="file"
                  accept=".pdf,.docx"
                  className="w-full text-sm"
                  onChange={(e) => {
                    const file = e.target.files?.[0] ?? null;
                    if (!file) return;
                    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
                    const format = JD_FORMAT_BY_EXTENSION[ext] ?? "pdf";
                    setJdFormat(format);
                    extractJd.mutate({ sourceFormat: format, file });
                  }}
                />
              </div>
              <div className="w-28">
                <Select value={jdFormat} onChange={(e) => setJdFormat(e.target.value as JdSourceFormat)}>
                  {JD_SOURCE_FORMATS.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </Select>
              </div>
            </div>
          </Field>
          {extractJd.isPending && (
            <p className="mt-2 text-xs" style={{ color: "var(--fg-subtle)" }}>
              Reading job description…
            </p>
          )}
          {extractJd.isError && (
            <div className="mt-2">
              <ErrorText onDismiss={() => extractJd.reset()}>
                {(extractJd.error as Error).message}
              </ErrorText>
            </div>
          )}
        </div>

        <div className="flex flex-wrap gap-3">
          <div className="w-52">
            <Field label="Company">
              <TextInput
                required
                value={form.company}
                onChange={(e) => setForm({ ...form, company: e.target.value })}
              />
            </Field>
          </div>
          <div className="w-52">
            <Field label="Designation">
              <TextInput
                required
                value={form.designation}
                onChange={(e) => setForm({ ...form, designation: e.target.value })}
              />
            </Field>
          </div>
          <div className="w-44">
            <Field label="Location">
              <TextInput
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
              />
            </Field>
          </div>
          <div className="w-44">
            <Suspense fallback={<DatePickerFieldSkeleton />}>
              <DatePickerField
                label="Application deadline"
                value={form.deadline}
                onValueChange={(deadline) => setForm({ ...form, deadline })}
              />
            </Suspense>
          </div>
        </div>

        <Field label="Job description">
          <TextArea
            required
            rows={8}
            placeholder="Paste the full job description here…"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </Field>

        {addJob.isError && (
          <ErrorText onDismiss={() => addJob.reset()}>
            {(addJob.error as Error).message}
          </ErrorText>
        )}

        <Button type="submit" disabled={addJob.isPending}>
          {addJob.isPending ? "Adding…" : "Add job"}
        </Button>
      </form>

      {data && !data.ranked && (
        <p className="mt-6 text-xs" style={{ color: "var(--fg-subtle)" }}>
          Complete your profile on the Settings page to get a personalized ranking and filter
          explanations here.
        </p>
      )}

      <div className="mt-6">
        {isPending ? (
          <p className="text-sm" style={{ color: "var(--fg-muted)" }}>
            Loading…
          </p>
        ) : !jobs || jobs.length === 0 ? (
          <EmptyState
            title="No jobs yet"
            hint="Paste a job description above to add one manually. Automatic discovery from job boards arrives in M2."
          />
        ) : (
          <ul className="space-y-3">
            {jobs.map((ranking) => (
              <JobRow
                key={ranking.job.id}
                ranking={ranking}
                showScore={data!.ranked}
                expanded={expandedJobId === ranking.job.id}
                onToggle={() =>
                  setExpandedJobId(expandedJobId === ranking.job.id ? null : ranking.job.id)
                }
              />
            ))}
          </ul>
        )}
      </div>
    </Page>
  );
}

function JobRow({
  ranking,
  showScore,
  expanded,
  onToggle,
}: {
  ranking: JobRanking;
  showScore: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { job } = ranking;
  const filtered = job.filtered_out_reason !== null;

  return (
    <li
      className="card-hover rounded-[var(--radius-input)] border"
      style={{
        borderColor: "var(--border)",
        background: "var(--canvas-subtle)",
        opacity: filtered ? 0.6 : 1,
      }}
    >
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        onClick={onToggle}
      >
        <span>
          <span className="text-sm font-medium">{job.designation}</span>
          <span className="ml-2 text-sm" style={{ color: "var(--fg-muted)" }}>
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
            {job.deadline ? ` · Due ${formatDeadline(job.deadline)}` : ""}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {showScore && !filtered && (
            <span
              className="rounded-[var(--radius-pill)] px-2.5 py-0.5 text-xs font-medium"
              style={{ background: "var(--accent-subtle)", color: "var(--accent)" }}
            >
              {formatPercent(ranking.overall_score)} match
            </span>
          )}
          <span className="text-xs" style={{ color: "var(--fg-subtle)" }}>
            {job.required_skill_ids.length} required skills
          </span>
        </span>
      </button>

      {filtered && (
        <p className="px-4 pb-3 text-xs" style={{ color: "var(--danger)" }}>
          Excluded: {job.filtered_out_reason}
        </p>
      )}
      {!filtered && ranking.soft_preference_reasons.length > 0 && (
        <p className="px-4 pb-3 text-xs" style={{ color: "var(--fg-subtle)" }}>
          {ranking.soft_preference_reasons.join(" · ")}
        </p>
      )}

      {expanded && (
        <div className="border-t px-4 py-3" style={{ borderColor: "var(--border)" }}>
          <RankedResumes jobId={job.id} />
        </div>
      )}
    </li>
  );
}

/** The M1 acceptance path (docs/roadmap.md): rank every resume in the library
 * against this job and show why each one scored the way it did. */
function RankedResumes({ jobId }: { jobId: number }) {
  const rank = useMutation({ mutationFn: () => rankResumesForJob(jobId) });

  if (!rank.data && !rank.isPending && !rank.isError) {
    return (
      <Button variant="secondary" onClick={() => rank.mutate()}>
        Rank my resumes against this job
      </Button>
    );
  }

  if (rank.isPending) {
    return (
      <p className="text-sm" style={{ color: "var(--fg-muted)" }}>
        Scoring…
      </p>
    );
  }

  if (rank.isError) {
    return <ErrorText onDismiss={() => rank.reset()}>{(rank.error as Error).message}</ErrorText>;
  }

  return (
    <Table>
      <TableHead columns={["Resume", "Match", "Skills", "Projects", "Experience", "Role"]} />
      <tbody>
        {rank.data!.map((m: MatchOut) => (
          <TableRow key={m.resume_id}>
            <TableCell>{m.resume_label}</TableCell>
            <TableCell mono>{formatPercent(m.personalized_score)}</TableCell>
            <TableCell mono>{formatPercent(m.explanation.skills.value)}</TableCell>
            <TableCell mono>{formatPercent(m.explanation.projects.value)}</TableCell>
            <TableCell mono>{formatPercent(m.explanation.experience.value)}</TableCell>
            <TableCell mono>{formatPercent(m.explanation.role.value)}</TableCell>
          </TableRow>
        ))}
      </tbody>
    </Table>
  );
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Matches DatePickerField's real label+control markup exactly (reusing the
 * same Field/TextInput this file already imports) so there's no layout
 * shift once the lazy chunk finishes loading -- not a from-scratch guess at
 * matching dimensions. */
function DatePickerFieldSkeleton() {
  return (
    <Field label="Application deadline">
      <TextInput disabled placeholder="Pick a date" />
    </Field>
  );
}

function formatDeadline(isoDate: string): string {
  // Parsed as UTC-midnight and displayed in the same zone to avoid an
  // off-by-one day from local-timezone conversion on a date-only value.
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}
