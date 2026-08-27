import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  DarkModeIcon,
  LightModeIcon,
  LinkIcon,
  LogoutIcon,
} from "@/components/icons";
import { Button, ErrorText } from "@/components/Form";
import { Page, SectionCard } from "@/components/Page";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  connectGmail,
  deleteAccount,
  disconnectGmail,
  getPlacementStatus,
  getProfile,
  getStatus,
  NotOnboardedError,
  putProfile,
} from "@/lib/api";
import { PALETTES, usePalette, type Palette } from "@/lib/palette";
import { useTheme } from "@/lib/theme";
import { DEFAULT_PREFERENCES, type ProfileIn } from "@/lib/types";

const PALETTE_LABELS: Record<Palette, string> = {
  violet: "Violet",
  ocean: "Ocean",
  meadow: "Meadow",
  terracotta: "Terracotta",
};

// Mirrors each palette's light-mode --accent value in styles/index.css --
// a display-only preview swatch, so it intentionally doesn't try to read the
// live custom property (which would require the palette to already be
// applied to compute). Keep in sync with index.css if either changes.
const PALETTE_SWATCH: Record<Palette, string> = {
  violet: "#5d4a9e",
  ocean: "#3a6ea8",
  meadow: "#3f7d4f",
  terracotta: "#b1592f",
};

export function Settings() {
  return (
    <Page title="Settings" description="Appearance, notifications, and connected accounts.">
      <div className="max-w-2xl space-y-6">
        <AppearanceSection />
        <NotificationsSection />
        <ConnectedAccountsSection />
        <AccountSection />
      </div>
    </Page>
  );
}

function AppearanceSection() {
  const { theme, toggleTheme } = useTheme();
  const { palette, setPalette } = usePalette();
  const isDark = theme === "dark";

  return (
    <SectionCard eyebrow="Appearance" eyebrowColor="var(--section-dashboard)" title="Theme & color">
      <div className="space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Dark mode</p>
            <p className="mt-0.5 text-xs" style={{ color: "var(--fg-subtle)" }}>
              {isDark ? "Currently dark." : "Currently light."} Follows your system until you choose
              one here.
            </p>
          </div>
          <Switch
            value={isDark}
            onToggle={(event) => toggleTheme({ x: event.clientX, y: event.clientY })}
            iconOn={<DarkModeIcon width={14} height={14} />}
            iconOff={<LightModeIcon width={14} height={14} />}
          />
        </div>

        <div>
          <p className="text-sm font-medium">Accent color</p>
          <p className="mt-0.5 text-xs" style={{ color: "var(--fg-subtle)" }}>
            Changes the accent used for buttons, active nav, and badges. Everything else about the
            look stays the same.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            {PALETTES.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPalette(p)}
                aria-label={`${PALETTE_LABELS[p]} accent`}
                aria-pressed={palette === p}
                title={PALETTE_LABELS[p]}
                className="palette-swatch h-9 w-9 rounded-full border-2"
                style={{
                  background: PALETTE_SWATCH[p],
                  borderColor: palette === p ? "var(--fg)" : "transparent",
                  transform: palette === p ? "scale(1.1)" : "scale(1)",
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

/** Writes to the same Preferences.notification_threshold field
 * placeinator.jobs.service.list_notifications reads -- the Dashboard's
 * notification panel and this slider share one real source of truth, not a
 * cosmetic control. */
function NotificationsSection() {
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: ["profile"],
    queryFn: getProfile,
    retry: (count, err) => !(err instanceof NotOnboardedError) && count < 2,
  });

  const [localThreshold, setLocalThreshold] = useState<number | null>(null);
  const active =
    localThreshold ??
    data?.preferences?.notification_threshold ??
    DEFAULT_PREFERENCES.notification_threshold;
  const saveTimer = useRef<number | null>(null);

  const mutation = useMutation({
    mutationFn: putProfile,
    onSuccess: (profile) => {
      queryClient.setQueryData(["profile"], profile);
      queryClient.invalidateQueries({ queryKey: ["jobs", "notifications"] });
      // Server data is now authoritative again; drop the local override so a
      // later external change to preferences (e.g. edited from the Profile
      // page) isn't shadowed by a stale drag value forever.
      setLocalThreshold(null);
    },
  });

  const scheduleSave = (value: number) => {
    setLocalThreshold(value);
    if (!data) return;
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    // Debounced, not saved on every tick while dragging -- a slider fires
    // dozens of change events per drag, and only the settled value matters.
    saveTimer.current = window.setTimeout(() => {
      const payload: ProfileIn = {
        full_name: data.full_name,
        email: data.email,
        phone: data.phone,
        college: data.college,
        department: data.department,
        student_id: data.student_id,
        neo_id: data.neo_id,
        name_aliases: data.name_aliases,
        preferences: { ...(data.preferences ?? DEFAULT_PREFERENCES), notification_threshold: value },
      };
      mutation.mutate(payload);
    }, 400);
  };

  return (
    <SectionCard eyebrow="Notifications" eyebrowColor="var(--section-jobs)" title="Match threshold">
      {!data && !isPending ? (
        <p className="text-sm" style={{ color: "var(--fg-subtle)" }}>
          Complete your{" "}
          <Link to="/profile" className="underline">
            profile
          </Link>{" "}
          first — notification preferences need an onboarded profile to attach to.
        </p>
      ) : (
        <div className="max-w-sm">
          <p className="text-sm" style={{ color: "var(--fg-muted)" }}>
            Only notify me about jobs that score at least{" "}
            <span className="font-semibold" style={{ color: "var(--fg)" }}>
              {Math.round(active * 100)}%
            </span>{" "}
            match.
          </p>
          <div className="mt-3">
            <Slider
              min={0}
              max={100}
              step={5}
              value={Math.round(active * 100)}
              disabled={!data}
              onValueChange={(value) => scheduleSave(value / 100)}
              aria-label="Minimum match score for notifications"
            />
          </div>
          <p className="mt-1 text-xs" style={{ color: "var(--fg-subtle)" }}>
            {mutation.isPending ? "Saving…" : " "}
          </p>
        </div>
      )}
    </SectionCard>
  );
}

/**
 * Google (Gmail & Calendar) is real M4 scope now -- connect/disconnect
 * actually work. Indeed/LinkedIn/Naukri still need no connected account
 * here; that distinction is spelled out rather than left implicit.
 */
function ConnectedAccountsSection() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["placement", "status"], queryFn: getPlacementStatus });

  const connect = useMutation({
    mutationFn: connectGmail,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["placement", "status"] }),
  });
  const disconnect = useMutation({
    mutationFn: disconnectGmail,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["placement", "status"] }),
  });

  const connected = data?.connected ?? false;

  return (
    <SectionCard
      eyebrow="Connected accounts"
      eyebrowColor="var(--section-placement)"
      title="Google, and job boards"
    >
      <div className="space-y-4">
        <div
          className="flex items-start justify-between gap-4 rounded-[var(--radius-input)] border p-3"
          style={{ borderColor: "var(--border)" }}
        >
          <div className="flex items-start gap-3">
            <LinkIcon width={18} height={18} style={{ color: "var(--fg-subtle)" }} />
            <div>
              <p className="text-sm font-medium">Google (Gmail & Calendar)</p>
              <p className="mt-1 text-xs" style={{ color: "var(--fg-subtle)" }}>
                Powers placement email monitoring and interview scheduling (spec §7).
              </p>
            </div>
          </div>
          {connected ? (
            <Button
              type="button"
              variant="secondary"
              className="shrink-0"
              disabled={disconnect.isPending}
              onClick={() => disconnect.mutate()}
            >
              {disconnect.isPending ? "Disconnecting…" : "Disconnect"}
            </Button>
          ) : (
            <Button
              type="button"
              variant="soft"
              className="shrink-0"
              disabled={connect.isPending}
              onClick={() => connect.mutate()}
            >
              {connect.isPending ? "Waiting for browser…" : "Connect"}
            </Button>
          )}
        </div>

        {connect.isError && (
          <ErrorText onDismiss={() => connect.reset()}>{(connect.error as Error).message}</ErrorText>
        )}

        <p className="text-xs" style={{ color: "var(--fg-subtle)" }}>
          Indeed, LinkedIn, and Naukri don't need a connected account here — searching them from
          the{" "}
          <Link to="/jobs" className="underline">
            Jobs page
          </Link>{" "}
          works without signing in, within what each site allows.
        </p>
      </div>
    </SectionCard>
  );
}

/** No account system exists in a local single-user app -- said plainly
 * rather than shipping a "Log out" button with nothing behind it. */
function AccountSection() {
  const { data } = useQuery({ queryKey: ["status"], queryFn: getStatus });

  return (
    <SectionCard eyebrow="Account" eyebrowColor="var(--fg-muted)" title="Local-only, no login">
      <div className="flex items-start gap-3">
        <LogoutIcon width={18} height={18} style={{ color: "var(--fg-subtle)" }} />
        <div className="text-sm" style={{ color: "var(--fg-muted)" }}>
          <p>
            PlaceInator runs entirely on this machine for one user. There's no account system, so
            there's nothing to log into or out of, and no password to manage.
          </p>
          {data && (
            <p className="selectable mt-2 text-xs" style={{ color: "var(--fg-subtle)" }}>
              Your data is stored locally at <span className="font-mono">{data.data_dir}</span>.
            </p>
          )}
        </div>
      </div>
      <div className="mt-5 border-t pt-5" style={{ borderColor: "var(--border)" }}>
        <DeleteAccountControl />
      </div>
    </SectionCard>
  );
}

/**
 * Two clicks to actually delete, on purpose -- the first reveals what it
 * does and asks the user to confirm; only the second one calls the API.
 * No modal (this app has none anywhere else -- ErrorText/inline-expansion is
 * the established pattern, see Field's own hint text and every route's
 * inline error states), just an inline warning panel that replaces the
 * button until the user commits or backs out.
 */
function DeleteAccountControl() {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const mutation = useMutation({
    mutationFn: deleteAccount,
    onSuccess: async () => {
      // Three things were tried, in order, each looking reasonable and each
      // failing in a different way -- caught by actually running this
      // against a real sidecar every time, the same way the earlier
      // Onboarding.tsx cache-timing bug was caught, not by reasoning about
      // React Query in the abstract:
      //
      // 1. queryClient.clear() empties the cache but doesn't reliably force
      //    App.tsx's still-mounted ["profile"] query to refetch.
      // 2. queryClient.invalidateQueries() *does* trigger a refetch, and the
      //    refetch *does* correctly 404 (confirmed via direct API check) --
      //    but React Query keeps a query's last-successful `data` around
      //    across a failed refetch by default. App.tsx's gate is
      //    `!data && error instanceof NotOnboardedError`; with `data` still
      //    holding the now-deleted profile, that check stayed false forever.
      // 3. removeQueries() + invalidateQueries() together raced each other:
      //    removeQueries on an active query already triggers its own
      //    refetch, and the second invalidateQueries's refetch for the same
      //    key aborted it (net::ERR_ABORTED, confirmed via network capture)
      //    with nothing to replace it -- the query was left with no data
      //    and no error at all, stuck.
      //
      // resetQueries() is the one built for exactly this: clears data AND
      // error back to a pristine state and triggers exactly one refetch for
      // the active observer, no race with a second call.
      await queryClient.resetQueries({ queryKey: ["profile"] });
    },
  });

  if (!confirming) {
    return (
      <Button variant="secondary" onClick={() => setConfirming(true)}>
        Delete account
      </Button>
    );
  }

  return (
    <div
      className="rounded-[var(--radius-input)] border p-4"
      style={{ borderColor: "var(--danger)", background: "color-mix(in srgb, var(--danger) 8%, transparent)" }}
    >
      <p className="text-sm font-medium" style={{ color: "var(--danger)" }}>
        This permanently deletes everything
      </p>
      <p className="mt-1 text-xs" style={{ color: "var(--fg-muted)" }}>
        Your profile, every resume, every job, all matches, tailored resumes, outreach drafts, and
        placement history: gone, and Google gets disconnected. This can't be undone. You'll land
        back on the welcome screen, same as a fresh install.
      </p>

      {mutation.isError && (
        <div className="mt-3">
          <ErrorText onDismiss={() => mutation.reset()}>{(mutation.error as Error).message}</ErrorText>
        </div>
      )}

      <div className="mt-3 flex gap-3">
        <Button variant="secondary" className="flex-1" onClick={() => setConfirming(false)}>
          Cancel
        </Button>
        <Button
          variant="danger"
          className="flex-1"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? "Deleting…" : "Yes, delete everything"}
        </Button>
      </div>
    </div>
  );
}
