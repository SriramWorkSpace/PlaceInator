import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button, ErrorText, Field, TextArea, TextInput } from "@/components/Form";
import { EmptyState, Page } from "@/components/Page";
import { Table, TableCell, TableHead, TableRow } from "@/components/Table";
import { createManualJob, listJobs, rankResumesForJob } from "@/lib/api";
import type { MatchOut } from "@/lib/types";

const EMPTY_JOB = { company: "", designation: "", location: "", description: "" };

export function Jobs() {
  const queryClient = useQueryClient();
  const { data: jobs, isPending } = useQuery({ queryKey: ["jobs"], queryFn: listJobs });
  const [form, setForm] = useState(EMPTY_JOB);
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);

  const addJob = useMutation({
    mutationFn: createManualJob,
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setForm(EMPTY_JOB);
      setExpandedJobId(job.id);
    },
  });

  return (
    <Page
      title="Job Intelligence"
      description="Paste a job description to match it against your resume library (spec §2)."
    >
      <form
        className="space-y-3 rounded-[var(--radius-panel)] border p-6"
        style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
        onSubmit={(e) => {
          e.preventDefault();
          addJob.mutate({
            company: form.company,
            designation: form.designation,
            description: form.description,
            location: form.location || null,
            url: null,
          });
        }}
      >
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
            {jobs.map((job) => (
              <li
                key={job.id}
                className="rounded-[var(--radius-input)] border"
                style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
              >
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-4 py-3 text-left"
                  onClick={() => setExpandedJobId(expandedJobId === job.id ? null : job.id)}
                >
                  <span>
                    <span className="text-sm font-medium">{job.designation}</span>
                    <span className="ml-2 text-sm" style={{ color: "var(--fg-muted)" }}>
                      {job.company}
                      {job.location ? ` · ${job.location}` : ""}
                    </span>
                  </span>
                  <span className="text-xs" style={{ color: "var(--fg-subtle)" }}>
                    {job.required_skill_ids.length} required skills
                  </span>
                </button>

                {expandedJobId === job.id && (
                  <div className="border-t px-4 py-3" style={{ borderColor: "var(--border)" }}>
                    <RankedResumes jobId={job.id} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Page>
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
