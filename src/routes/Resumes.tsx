import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button, ErrorText, Field, Select, TextInput } from "@/components/Form";
import { EmptyState, Page } from "@/components/Page";
import { Table, TableCell, TableHead, TableRow } from "@/components/Table";
import { listResumes, uploadResume } from "@/lib/api";
import { SOURCE_FORMATS, type SourceFormat } from "@/lib/types";

export function Resumes() {
  const queryClient = useQueryClient();
  const { data: resumes, isPending } = useQuery({ queryKey: ["resumes"], queryFn: listResumes });

  const [label, setLabel] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [sourceFormat, setSourceFormat] = useState<SourceFormat>("pdf");
  const fileInput = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: uploadResume,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resumes"] });
      setLabel("");
      setTargetRole("");
      if (fileInput.current) fileInput.current.value = "";
    },
  });

  return (
    <Page title="Resume Library" description="Your role-specific resume library (spec §3).">
      <form
        className="flex flex-wrap items-end gap-3 rounded-[var(--radius-panel)] border p-6"
        style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
        onSubmit={(e) => {
          e.preventDefault();
          const file = fileInput.current?.files?.[0];
          if (!file) return;
          mutation.mutate({ label, sourceFormat, targetRole: targetRole || undefined, file });
        }}
      >
        <div className="w-40">
          <Field label="Label">
            <TextInput
              required
              placeholder="SDE Resume"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </Field>
        </div>
        <div className="w-44">
          <Field label="Target role">
            <TextInput
              placeholder="Backend Engineer"
              value={targetRole}
              onChange={(e) => setTargetRole(e.target.value)}
            />
          </Field>
        </div>
        <div className="w-28">
          <Field label="Format">
            <Select
              value={sourceFormat}
              onChange={(e) => setSourceFormat(e.target.value as SourceFormat)}
            >
              {SOURCE_FORMATS.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="flex-1 min-w-48">
          <Field label="File">
            <input
              ref={fileInput}
              type="file"
              required
              accept=".pdf,.docx,.tex"
              className="w-full text-sm"
            />
          </Field>
        </div>
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Uploading…" : "Upload"}
        </Button>
      </form>

      {mutation.isError && (
        <div className="mt-2">
          <ErrorText onDismiss={() => mutation.reset()}>
            {(mutation.error as Error).message}
          </ErrorText>
        </div>
      )}

      <div className="mt-6">
        {isPending ? (
          <p className="text-sm" style={{ color: "var(--fg-muted)" }}>
            Loading…
          </p>
        ) : !resumes || resumes.length === 0 ? (
          <EmptyState
            title="No resumes yet"
            hint="Upload a PDF, DOCX, or LaTeX resume above. Each one is parsed into skills, projects, and experience so jobs can be matched against all of them."
          />
        ) : (
          <Table>
            <TableHead columns={["Label", "Target role", "Format", "Version", "Chunks"]} />
            <tbody>
              {resumes.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.label}</TableCell>
                  <TableCell>{r.target_role ?? "—"}</TableCell>
                  <TableCell mono>{r.source_format}</TableCell>
                  <TableCell mono>v{r.version}</TableCell>
                  <TableCell mono>{r.chunk_count}</TableCell>
                </TableRow>
              ))}
            </tbody>
          </Table>
        )}
      </div>
    </Page>
  );
}
