import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button, ErrorText, Field, Select, TextInput } from "@/components/Form";
import { Page } from "@/components/Page";
import { getProfile, NotOnboardedError, putProfile } from "@/lib/api";
import { DEFAULT_PREFERENCES, type ProfileIn, type ProfileOut, type WorkMode } from "@/lib/types";

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

  const mutation = useMutation({
    mutationFn: putProfile,
    onSuccess: (profile) => {
      queryClient.setQueryData(["profile"], profile);
      setForm(null);
    },
  });

  if (isPending) {
    return (
      <Page title="Settings" description="Profile, preferences, and employment constraints.">
        <p className="text-sm" style={{ color: "var(--fg-muted)" }}>
          Loading…
        </p>
      </Page>
    );
  }

  return (
    <Page
      title="Settings"
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

        {mutation.isError && <ErrorText>{(mutation.error as Error).message}</ErrorText>}

        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : data ? "Save changes" : "Complete onboarding"}
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
