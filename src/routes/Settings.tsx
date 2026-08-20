import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button, ErrorText, Field, Select, TextInput } from "@/components/Form";
import { Page } from "@/components/Page";
import {
  extractProfileFromResume,
  getProfile,
  NotOnboardedError,
  putProfile,
  uploadResume,
} from "@/lib/api";
import {
  DEFAULT_PREFERENCES,
  SOURCE_FORMATS,
  type ProfileIn,
  type ProfileOut,
  type SourceFormat,
  type WorkMode,
} from "@/lib/types";

const EMPTY_FORM: ProfileIn = {
  full_name: "",
  email: "",
  phone: null,
  college: null,
  department: null,
  student_id: null,
  name_aliases: [],
  preferences: DEFAULT_PREFERENCES,
};

const FORMAT_BY_EXTENSION: Record<string, SourceFormat> = {
  pdf: "pdf",
  docx: "docx",
  tex: "tex",
};

export function Settings() {
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: ["profile"],
    queryFn: getProfile,
    retry: (count, err) => !(err instanceof NotOnboardedError) && count < 2,
  });

  const [form, setForm] = useState<ProfileIn | null>(null);
  // Seed local form state once from the server response; afterwards the form
  // is the source of truth until the user saves.
  const active = form ?? (data ? toForm(data) : EMPTY_FORM);

  // Onboarding-only: a resume staged here is uploaded as the primary resume
  // right after the profile itself is saved.
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeFormat, setResumeFormat] = useState<SourceFormat>("pdf");
  const fileInput = useRef<HTMLInputElement>(null);

  const extractMutation = useMutation({
    mutationFn: extractProfileFromResume,
    onSuccess: (fields) => {
      // Only fill fields the user hasn't already typed something into --
      // autofill should never clobber a manual edit.
      setForm({
        ...active,
        full_name: active.full_name || fields.full_name || "",
        email: active.email || fields.email || "",
        phone: active.phone || fields.phone,
        college: active.college || fields.college,
        department: active.department || fields.department,
      });
    },
  });

  const uploadPrimaryMutation = useMutation({
    mutationFn: uploadResume,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resumes"] });
    },
  });

  const mutation = useMutation({
    mutationFn: putProfile,
    onSuccess: async (profile) => {
      queryClient.setQueryData(["profile"], profile);
      setForm(null);

      if (resumeFile) {
        await uploadPrimaryMutation.mutateAsync({
          label: "Primary Resume",
          sourceFormat: resumeFormat,
          isPrimary: true,
          file: resumeFile,
        });
        setResumeFile(null);
        if (fileInput.current) fileInput.current.value = "";
      }
    },
  });

  if (isPending) {
    return (
      <Page title="Profile & Preferences" description="Profile, preferences, and employment constraints.">
        <p className="text-sm" style={{ color: "var(--fg-muted)" }}>
          Loading…
        </p>
      </Page>
    );
  }

  const saving = mutation.isPending || uploadPrimaryMutation.isPending;

  return (
    <Page
      title="Profile & Preferences"
      description={
        data
          ? "Your profile is complete. Anything here can be edited and re-saved."
          : "Complete onboarding to start adding resumes and matching against jobs."
      }
    >
      <form
        className="max-w-xl space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(active);
        }}
      >
        {!data && (
          <div
            className="card rounded-[var(--radius-panel)] border p-4"
            style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
          >
            <Field
              label="Autofill from a resume (optional)"
              hint="Upload a resume to prefill the fields below. It's saved as your primary resume once you complete onboarding."
            >
              <div className="flex flex-wrap items-end gap-3">
                <div className="min-w-48 flex-1">
                  <input
                    ref={fileInput}
                    type="file"
                    accept=".pdf,.docx,.tex"
                    className="w-full text-sm"
                    onChange={(e) => {
                      const file = e.target.files?.[0] ?? null;
                      setResumeFile(file);
                      if (!file) return;
                      const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
                      const format = FORMAT_BY_EXTENSION[ext] ?? "pdf";
                      setResumeFormat(format);
                      extractMutation.mutate({ sourceFormat: format, file });
                    }}
                  />
                </div>
                <div className="w-28">
                  <Select
                    value={resumeFormat}
                    onChange={(e) => setResumeFormat(e.target.value as SourceFormat)}
                  >
                    {SOURCE_FORMATS.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>
            </Field>
            {extractMutation.isPending && (
              <p className="mt-2 text-xs" style={{ color: "var(--fg-subtle)" }}>
                Reading resume…
              </p>
            )}
            {extractMutation.isError && (
              <div className="mt-2">
                <ErrorText onDismiss={() => extractMutation.reset()}>
                  {(extractMutation.error as Error).message}
                </ErrorText>
              </div>
            )}
          </div>
        )}

        <Field label="Full name">
          <TextInput
            required
            value={active.full_name}
            onChange={(e) => setForm({ ...active, full_name: e.target.value })}
          />
        </Field>

        <Field label="Email">
          <TextInput
            type="email"
            required
            value={active.email}
            onChange={(e) => setForm({ ...active, email: e.target.value })}
          />
        </Field>

        <Field label="College" hint="Used to help identify you in placement documents (spec §7).">
          <TextInput
            value={active.college ?? ""}
            onChange={(e) => setForm({ ...active, college: e.target.value || null })}
          />
        </Field>

        <Field label="Target roles" hint="Comma-separated, e.g. Backend Engineer, SDE">
          <TextInput
            value={active.preferences.target_roles.join(", ")}
            onChange={(e) =>
              setForm({
                ...active,
                preferences: {
                  ...active.preferences,
                  target_roles: splitList(e.target.value),
                },
              })
            }
          />
        </Field>

        <Field label="Work mode">
          <Select
            value={active.preferences.work_mode}
            onChange={(e) =>
              setForm({
                ...active,
                preferences: { ...active.preferences, work_mode: e.target.value as WorkMode },
              })
            }
          >
            <option value="any">Any</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On-site</option>
          </Select>
        </Field>

        <Field label="Minimum acceptable salary" hint="Jobs below this are excluded, not just ranked lower.">
          <TextInput
            type="number"
            min={0}
            value={active.preferences.min_salary ?? ""}
            onChange={(e) =>
              setForm({
                ...active,
                preferences: {
                  ...active.preferences,
                  min_salary: e.target.value ? Number(e.target.value) : null,
                },
              })
            }
          />
        </Field>

        {(mutation.isError || uploadPrimaryMutation.isError) && (
          <ErrorText
            onDismiss={() => {
              mutation.reset();
              uploadPrimaryMutation.reset();
            }}
          >
            {((mutation.error ?? uploadPrimaryMutation.error) as Error).message}
          </ErrorText>
        )}

        <Button type="submit" disabled={saving}>
          {saving ? "Saving…" : data ? "Save changes" : "Complete onboarding"}
        </Button>
      </form>
    </Page>
  );
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function toForm(profile: ProfileOut): ProfileIn {
  return {
    full_name: profile.full_name,
    email: profile.email,
    phone: profile.phone,
    college: profile.college,
    department: profile.department,
    student_id: profile.student_id,
    name_aliases: profile.name_aliases,
    preferences: profile.preferences ?? DEFAULT_PREFERENCES,
  };
}
