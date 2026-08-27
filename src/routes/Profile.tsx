import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button, ErrorText, Field, Select, TextInput } from "@/components/Form";
import { NameFields } from "@/components/NameFields";
import { Page, SectionCard } from "@/components/Page";
import { RolePicker } from "@/components/ui/role-picker";
import {
  extractProfileFromResume,
  getProfile,
  NotOnboardedError,
  putProfile,
  uploadResume,
} from "@/lib/api";
import { composeFullName, EMPTY_NAME_PARTS, isEmptyName, splitFullName, type NameParts } from "@/lib/name";
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
  neo_id: null,
  name_aliases: [],
  preferences: DEFAULT_PREFERENCES,
};

const FORMAT_BY_EXTENSION: Record<string, SourceFormat> = {
  pdf: "pdf",
  docx: "docx",
  tex: "tex",
};

export function Profile() {
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

  // First/middle/last are structured, optional supplementary fields (see
  // src/lib/name.ts) -- kept separate from the actual `full_name` the user
  // types below. They're folded into `name_aliases` at submit time (see
  // onSubmit) rather than composing `full_name`, so filling them in still
  // does something even though full_name is now independently authored.
  const [nameParts, setNameParts] = useState<NameParts | null>(null);
  const activeNameParts = nameParts ?? EMPTY_NAME_PARTS;

  // The primary display/matching name -- manually typed, not derived from
  // the fields above. Seeded once from the server response, then its own
  // source of truth until save, same pattern as `form`/`active`.
  const [fullName, setFullName] = useState<string | null>(null);
  const activeFullName = fullName ?? (data ? data.full_name : "");

  // Onboarding-only: a resume staged here is uploaded as the primary resume
  // right after the profile itself is saved.
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeFormat, setResumeFormat] = useState<SourceFormat>("pdf");
  const fileInput = useRef<HTMLInputElement>(null);

  const [justSaved, setJustSaved] = useState(false);

  const extractMutation = useMutation({
    mutationFn: extractProfileFromResume,
    onSuccess: (fields) => {
      // Only fill fields the user hasn't already typed something into --
      // autofill should never clobber a manual edit.
      setForm({
        ...active,
        email: active.email || fields.email || "",
        phone: active.phone || fields.phone,
        college: active.college || fields.college,
        department: active.department || fields.department,
      });
      if (!activeFullName && fields.full_name) {
        setFullName(fields.full_name);
      }
      if (isEmptyName(activeNameParts) && fields.full_name) {
        setNameParts(splitFullName(fields.full_name));
      }
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
      setNameParts(null);
      setFullName(null);

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

      // Quiet, self-clearing confirmation rather than a persistent banner --
      // the save already closed the loop (button label reverts, form is no
      // longer dirty); this just confirms the click landed.
      setJustSaved(true);
      window.setTimeout(() => setJustSaved(false), 2000);
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
          // Structured first/middle/last are folded into name_aliases
          // (rather than composing full_name) so they still do something
          // once entered, even though full_name is typed independently.
          const alias = composeFullName(activeNameParts);
          const existingAliases = active.name_aliases;
          const isNewAlias =
            alias.length > 0 &&
            alias.toLowerCase() !== activeFullName.trim().toLowerCase() &&
            !existingAliases.some((a) => a.toLowerCase() === alias.toLowerCase());
          mutation.mutate({
            ...active,
            full_name: activeFullName,
            name_aliases: isNewAlias ? [...existingAliases, alias] : existingAliases,
          });
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

        <SectionCard eyebrow="Identity" eyebrowColor="var(--fg-muted)" title="Who you are">
          <div className="space-y-4">
            <NameFields parts={activeNameParts} onChange={setNameParts} />

            <Field label="Full name" hint="Shown and matched across the app.">
              <TextInput
                required
                placeholder="Enter full name"
                value={activeFullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </Field>

            <Field label="Email">
              <TextInput
                type="email"
                required
                placeholder="Enter email address"
                value={active.email}
                onChange={(e) => setForm({ ...active, email: e.target.value })}
              />
            </Field>

            <Field label="College" hint="Used to help identify you in placement documents (spec §7).">
              <TextInput
                placeholder="Enter college or university"
                value={active.college ?? ""}
                onChange={(e) => setForm({ ...active, college: e.target.value || null })}
              />
            </Field>

            <Field
              label="Registration number"
              hint="Used to match you in placement-sheet attachments. Entered in uppercase automatically."
            >
              <TextInput
                placeholder="Enter registration number"
                value={active.student_id ?? ""}
                onChange={(e) =>
                  setForm({ ...active, student_id: e.target.value.toUpperCase() || null })
                }
              />
            </Field>

            <Field
              label="Neo ID"
              hint="Your campus portal ID, if your college uses one alongside a registration number. Also used for placement-sheet matching. Entered in uppercase automatically."
            >
              <TextInput
                placeholder="Enter Neo ID"
                value={active.neo_id ?? ""}
                onChange={(e) => setForm({ ...active, neo_id: e.target.value.toUpperCase() || null })}
              />
            </Field>
          </div>
        </SectionCard>

        <SectionCard eyebrow="Preferences" eyebrowColor="var(--accent)" title="What you're looking for">
          <div className="space-y-4">
            <Field label="Target roles" hint="Pick from suggestions or type your own and press Enter.">
              <RolePicker
                value={active.preferences.target_roles}
                onValueChange={(target_roles) =>
                  setForm({
                    ...active,
                    preferences: { ...active.preferences, target_roles },
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
                placeholder="No minimum"
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
          </div>
        </SectionCard>

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

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={saving}>
            {saving ? "Saving…" : data ? "Save changes" : "Complete onboarding"}
          </Button>
          <span
            className="text-xs transition-opacity duration-200"
            style={{ color: "var(--success)", opacity: justSaved ? 1 : 0 }}
            aria-live="polite"
          >
            {justSaved ? "Saved" : ""}
          </span>
        </div>
      </form>
    </Page>
  );
}

function toForm(profile: ProfileOut): ProfileIn {
  return {
    full_name: profile.full_name,
    email: profile.email,
    phone: profile.phone,
    college: profile.college,
    department: profile.department,
    student_id: profile.student_id,
    neo_id: profile.neo_id,
    name_aliases: profile.name_aliases,
    preferences: profile.preferences ?? DEFAULT_PREFERENCES,
  };
}
