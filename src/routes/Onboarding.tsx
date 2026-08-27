import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import logo from "@/assets/logo.png";
import { CheckCircleIcon, LinkIcon } from "@/components/icons";
import { Button, ErrorText, Field, Select, TextInput } from "@/components/Form";
import { NameFields } from "@/components/NameFields";
import { RolePicker } from "@/components/ui/role-picker";
import {
  connectGmail,
  extractProfileFromResume,
  putProfile,
  uploadResume,
} from "@/lib/api";
import { composeFullName, EMPTY_NAME_PARTS, isEmptyName, splitFullName, type NameParts } from "@/lib/name";
import { DEFAULT_PREFERENCES, SOURCE_FORMATS, type ProfileIn, type SourceFormat } from "@/lib/types";

// Same curve AppShell's own step/route transitions use (styles/index.css's
// --ease-out) -- Motion's transition prop needs the literal array, not the
// CSS var, so it's duplicated rather than forked into a different feel.
const EASE_OUT: [number, number, number, number] = [0.23, 1, 0.32, 1];

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

const STEPS = ["Welcome", "Connect Google", "Your profile", "Ready"] as const;

/**
 * The very first thing a fresh install shows -- gates the whole app in
 * App.tsx until a profile exists (getProfile 404s with NotOnboardedError).
 * A full-screen takeover, not routed under AppShell: there's no sidebar to
 * navigate to yet, and the point is to remove every choice except "get set
 * up" until that's done.
 *
 * Ordered the way most apps sequence first-run setup -- sign in, then fill
 * in your details, then land in the app -- with "sign in" meaning "connect
 * Google" here. Profile is the only one of the two the backend actually
 * requires (every feature 412s without it); Google stays genuinely
 * skippable rather than a hard login gate, same as it already is from
 * Settings -- forcing it would trap a fresh install behind Google's own
 * OAuth-verification screen (a real 403 hit once already this session) with
 * no way into the app at all. Bookended by a greeting and a confirmation so
 * the whole thing reads as one guided arrival rather than a form dropped on
 * the user.
 */
export function Onboarding() {
  const [step, setStep] = useState(0);
  const [connected, setConnected] = useState(false);
  const queryClient = useQueryClient();
  const reduceMotion = useReducedMotion();

  const finish = () => {
    // The profile row already exists in the query cache (ProfileStep's
    // mutation set it directly) -- this just tells App.tsx's gating query to
    // read it, swapping Onboarding out for the real router with no reload.
    queryClient.invalidateQueries({ queryKey: ["profile"] });
  };

  return (
    <div
      className="flex h-full items-center justify-center overflow-y-auto p-6"
      style={{ background: "var(--canvas)" }}
    >
      <div className="w-full max-w-lg">
        <StepDots current={step} />
        <div
          className="card mt-6 rounded-[var(--radius-panel)] border p-8"
          style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={step}
              initial={{ opacity: 0, y: reduceMotion ? 0 : 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: reduceMotion ? 0 : 0.22, ease: EASE_OUT } }}
              exit={{ opacity: 0, y: reduceMotion ? 0 : -8, transition: { duration: reduceMotion ? 0 : 0.16, ease: EASE_OUT } }}
            >
              {step === 0 && <WelcomeStep onNext={() => setStep(1)} />}
              {step === 1 && (
                <ConnectStep
                  connected={connected}
                  onConnected={() => setConnected(true)}
                  onNext={() => setStep(2)}
                />
              )}
              {step === 2 && <ProfileStep onNext={() => setStep(3)} />}
              {step === 3 && <DoneStep connected={connected} onEnter={finish} />}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

function StepDots({ current }: { current: number }) {
  return (
    <div className="flex items-center justify-center gap-2" role="progressbar" aria-valuenow={current + 1} aria-valuemin={1} aria-valuemax={STEPS.length}>
      {STEPS.map((label, i) => (
        <span key={label} className="flex items-center gap-2">
          <span
            className="h-1.5 rounded-full transition-all duration-300"
            style={{
              width: i === current ? "1.75rem" : "0.4rem",
              background: i <= current ? "var(--accent)" : "var(--border-strong)",
            }}
            aria-hidden="true"
          />
        </span>
      ))}
    </div>
  );
}

function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="text-center">
      <img src={logo} alt="" className="mx-auto h-14 w-14" aria-hidden="true" />
      <h1 className="display-heading mt-5 text-3xl">Welcome to PlaceInator</h1>
      <p className="mx-auto mt-3 max-w-sm text-sm" style={{ color: "var(--fg-muted)" }}>
        Your local placement companion. Resumes, job matching, tailoring, and
        placement tracking, all running on this machine, nothing sent
        anywhere else.
      </p>
      <Button className="mt-8 w-full" onClick={onNext}>
        Get started
      </Button>
      <p className="mt-3 text-xs" style={{ color: "var(--fg-subtle)" }}>
        Takes about a minute.
      </p>
    </div>
  );
}

function ProfileStep({ onNext }: { onNext: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProfileIn>(EMPTY_FORM);
  const [nameParts, setNameParts] = useState<NameParts>(EMPTY_NAME_PARTS);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeFormat, setResumeFormat] = useState<SourceFormat>("pdf");
  const fileInput = useRef<HTMLInputElement>(null);

  const extractMutation = useMutation({
    mutationFn: extractProfileFromResume,
    onSuccess: (fields) => {
      // Never clobber something the user already typed.
      setForm((prev) => ({
        ...prev,
        full_name: prev.full_name || fields.full_name || "",
        email: prev.email || fields.email || "",
        college: prev.college || fields.college,
      }));
      if (isEmptyName(nameParts) && fields.full_name) {
        setNameParts(splitFullName(fields.full_name));
      }
    },
  });

  const uploadPrimaryMutation = useMutation({ mutationFn: uploadResume });

  const saveMutation = useMutation({
    mutationFn: putProfile,
    // Deliberately does NOT write into the ["profile"] query cache here --
    // that's the same key App.tsx watches to decide whether to show
    // Onboarding at all, and setting it this early flipped that gate the
    // instant this step saved, skipping straight to the real dashboard and
    // silently dropping the Connect Google / Done steps below. The cache
    // gets populated for real once the whole wizard finishes (see
    // Onboarding()'s finish(), which invalidates the same key) -- confirmed
    // with a real Playwright run against a real sidecar, not just reasoned
    // about: this exact line reproduced the "skips straight to dashboard"
    // bug being fixed here.
    onSuccess: async () => {
      if (resumeFile) {
        await uploadPrimaryMutation.mutateAsync({
          label: "Primary Resume",
          sourceFormat: resumeFormat,
          isPrimary: true,
          file: resumeFile,
        });
        queryClient.invalidateQueries({ queryKey: ["resumes"] });
      }
      onNext();
    },
  });

  const saving = saveMutation.isPending || uploadPrimaryMutation.isPending;

  return (
    <div>
      <p className="eyebrow" style={{ color: "var(--accent)" }}>
        Step 3 of 4
      </p>
      <h2 className="display-heading mt-1 text-2xl">Tell us about you</h2>
      <p className="mt-1.5 text-sm" style={{ color: "var(--fg-muted)" }}>
        This is what every match, tailored resume, and recommendation is measured against.
      </p>

      <form
        className="mt-6 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          // Structured first/middle/last are folded into name_aliases
          // (rather than composing full_name) so they still do something
          // even though full_name is typed independently below.
          const alias = composeFullName(nameParts);
          const isNewAlias =
            alias.length > 0 &&
            alias.toLowerCase() !== form.full_name.trim().toLowerCase() &&
            !form.name_aliases.some((a) => a.toLowerCase() === alias.toLowerCase());
          saveMutation.mutate({
            ...form,
            name_aliases: isNewAlias ? [...form.name_aliases, alias] : form.name_aliases,
          });
        }}
      >
        <div
          className="rounded-[var(--radius-input)] border p-4"
          style={{ borderColor: "var(--border)", background: "var(--canvas)" }}
        >
          <Field
            label="Autofill from a resume (optional)"
            hint="Upload a resume and we'll fill in what we can find below."
          >
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-40 flex-1">
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
              <div className="w-24">
                <Select value={resumeFormat} onChange={(e) => setResumeFormat(e.target.value as SourceFormat)}>
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
              Reading resume&hellip;
            </p>
          )}
        </div>

        <NameFields parts={nameParts} onChange={setNameParts} />

        <Field label="Full name">
          <TextInput
            required
            placeholder="Enter full name"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          />
        </Field>

        <Field label="Email">
          <TextInput
            type="email"
            required
            placeholder="Enter email address"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </Field>

        <Field label="College" hint="Helps identify you in placement documents. Optional.">
          <TextInput
            placeholder="Enter college or university"
            value={form.college ?? ""}
            onChange={(e) => setForm({ ...form, college: e.target.value || null })}
          />
        </Field>

        <Field
          label="Registration number"
          hint="Used to match you in placement-sheet attachments. Optional, add anytime. Entered in uppercase automatically."
        >
          <TextInput
            placeholder="Enter registration number"
            value={form.student_id ?? ""}
            onChange={(e) => setForm({ ...form, student_id: e.target.value.toUpperCase() || null })}
          />
        </Field>

        <Field
          label="Neo ID"
          hint="Your campus portal ID, if your college uses one alongside a registration number. Optional, add anytime. Entered in uppercase automatically."
        >
          <TextInput
            placeholder="Enter Neo ID"
            value={form.neo_id ?? ""}
            onChange={(e) => setForm({ ...form, neo_id: e.target.value.toUpperCase() || null })}
          />
        </Field>

        <Field label="Target roles" hint="Pick from suggestions or type your own and press Enter. Optional, add anytime.">
          <RolePicker
            value={form.preferences.target_roles}
            onValueChange={(target_roles) =>
              setForm({
                ...form,
                preferences: { ...form.preferences, target_roles },
              })
            }
          />
        </Field>

        {(saveMutation.isError || uploadPrimaryMutation.isError) && (
          <ErrorText
            onDismiss={() => {
              saveMutation.reset();
              uploadPrimaryMutation.reset();
            }}
          >
            {((saveMutation.error ?? uploadPrimaryMutation.error) as Error).message}
          </ErrorText>
        )}

        <Button type="submit" className="w-full" disabled={saving}>
          {saving ? "Saving…" : "Continue"}
        </Button>
      </form>
    </div>
  );
}

function ConnectStep({
  connected,
  onConnected,
  onNext,
}: {
  connected: boolean;
  onConnected: () => void;
  onNext: () => void;
}) {
  const connect = useMutation({
    mutationFn: connectGmail,
    onSuccess: onConnected,
  });

  return (
    <div>
      <p className="eyebrow" style={{ color: "var(--accent)" }}>
        Step 2 of 4
      </p>
      <h2 className="display-heading mt-1 text-2xl">Sign in with Google</h2>
      <p className="mt-1.5 text-sm" style={{ color: "var(--fg-muted)" }}>
        Optional. Lets PlaceInator watch for placement-cell emails and add
        confirmed interview events straight to your calendar. You can connect
        this later from Settings just as easily, nothing past this step
        needs it.
      </p>

      <div
        className="mt-6 flex items-start gap-3 rounded-[var(--radius-input)] border p-4"
        style={{ borderColor: "var(--border)", background: "var(--canvas)" }}
      >
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
          style={{ background: "var(--accent-subtle)" }}
        >
          {connected ? (
            <CheckCircleIcon width={18} height={18} style={{ color: "var(--success)" }} />
          ) : (
            <LinkIcon width={18} height={18} style={{ color: "var(--accent)" }} />
          )}
        </span>
        <div>
          <p className="text-sm font-medium">
            {connected ? "Connected" : "Google (Gmail & Calendar)"}
          </p>
          <p className="mt-1 text-xs" style={{ color: "var(--fg-subtle)" }}>
            {connected
              ? "You're all set. Placement email monitoring is live."
              : "Opens your browser for Google's own sign-in screen."}
          </p>
        </div>
      </div>

      {connect.isError && (
        <div className="mt-3">
          <ErrorText onDismiss={() => connect.reset()}>{(connect.error as Error).message}</ErrorText>
        </div>
      )}

      <div className="mt-6 flex gap-3">
        {connected ? (
          <Button className="w-full" onClick={onNext}>
            Continue
          </Button>
        ) : (
          <>
            <Button variant="secondary" className="flex-1" onClick={onNext}>
              Skip for now
            </Button>
            <Button
              variant="primary"
              className="flex-1"
              disabled={connect.isPending}
              onClick={() => connect.mutate()}
            >
              {connect.isPending ? "Waiting for browser…" : "Connect"}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function DoneStep({ connected, onEnter }: { connected: boolean; onEnter: () => void }) {
  return (
    <div className="text-center">
      <span
        className="mx-auto flex h-14 w-14 items-center justify-center rounded-full"
        style={{ background: "var(--accent-subtle)" }}
      >
        <CheckCircleIcon width={28} height={28} style={{ color: "var(--success)" }} />
      </span>
      <h2 className="display-heading mt-5 text-2xl">You're all set</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm" style={{ color: "var(--fg-muted)" }}>
        Your profile is saved{connected ? " and Google is connected" : ""}. Add
        a resume, paste a job description, and PlaceInator will start ranking
        matches right away.
      </p>
      <Button className="mt-8 w-full" onClick={onEnter}>
        Enter PlaceInator
      </Button>
    </div>
  );
}
