import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/Form";
import { GroupsIcon, HomeIcon, ResumeDocIcon, SearchIcon } from "@/components/icons";
import { EmptyState, Page, SectionCard } from "@/components/Page";
import {
  getStatus,
  listJobNotifications,
  listJobs,
  listResumes,
  markNotificationSeen,
  NotOnboardedError,
  SidecarUnavailableError,
} from "@/lib/api";
import type { JobRanking } from "@/lib/types";

export function Dashboard() {
  const { data: notifications, isPending } = useQuery({
    queryKey: ["jobs", "notifications"],
    queryFn: listJobNotifications,
    retry: (count, err) => !(err instanceof NotOnboardedError) && count < 2,
  });
  const hasNotifications = !!notifications && notifications.length > 0;

  return (
    <Page
      title="Studio Overview"
      description="Your placement activity at a glance: profile, resumes, jobs, and the local engine that ties them together."
    >
      <KpiRow notificationCount={notifications?.length ?? 0} />
      <div className="mt-6">
        <SidecarStatus />
      </div>
      <div className="mt-6">
        {hasNotifications ? (
          <Notifications notifications={notifications} />
        ) : (
          !isPending && (
            <EmptyState
              title="Nothing to show yet"
              hint="Complete onboarding and add a resume to start seeing matched opportunities and upcoming placement events here."
            />
          )
        )}
      </div>
    </Page>
  );
}

/**
 * "At a glance" per this page's own description, but until now it showed
 * zero numbers -- everything numeric (resume count, job count, new matches)
 * was either absent or buried a click away. Three stat tiles, each backed by
 * a query this app already has (listResumes/listJobs are plain GETs, no new
 * endpoint), each tinted with its own section's own nav color so a tile
 * reads as "the Resumes number" / "the Jobs number" at a glance -- the same
 * per-section-color convention src/lib/nav.ts already drives everywhere else.
 */
function KpiRow({ notificationCount }: { notificationCount: number }) {
  const { data: resumes } = useQuery({ queryKey: ["resumes"], queryFn: listResumes });
  const { data: jobs } = useQuery({ queryKey: ["jobs"], queryFn: listJobs });

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <StatTile
        icon={ResumeDocIcon}
        color="var(--section-resumes)"
        label="Resumes"
        value={resumes?.length}
      />
      <StatTile icon={SearchIcon} color="var(--section-jobs)" label="Jobs tracked" value={jobs?.length} />
      <StatTile
        icon={GroupsIcon}
        color="var(--section-outreach)"
        label="New matches"
        value={notificationCount}
      />
    </div>
  );
}

function StatTile({
  icon: Icon,
  color,
  label,
  value,
}: {
  icon: typeof HomeIcon;
  color: string;
  label: string;
  value: number | undefined;
}) {
  return (
    <div
      className="card rounded-[var(--radius-panel)] border p-5"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <div className="flex items-center gap-2.5">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
          style={{ background: `color-mix(in srgb, ${color} 20%, transparent)` }}
        >
          <Icon width={16} height={16} style={{ color }} />
        </span>
        <span className="eyebrow" style={{ color }}>
          {label}
        </span>
      </div>
      <p className="display-heading mt-3 text-4xl" aria-live="polite">
        {value === undefined ? (
          <span aria-hidden="true" style={{ color: "var(--fg-subtle)" }}>
            &ndash;
          </span>
        ) : (
          value
        )}
      </p>
    </div>
  );
}

/**
 * Personalized job notifications (spec §2): jobs that cleared hard filters
 * and the match threshold, each with the soft-preference reasons that made
 * it relevant -- explaining *why*, not just surfacing a bare list. Dismissing
 * one calls the same "mark seen" endpoint the Jobs page's ranked list already
 * reads Job.filtered_out_reason from, so it never reappears here once acted on.
 */
function Notifications({ notifications }: { notifications: JobRanking[] }) {
  const queryClient = useQueryClient();
  const markSeen = useMutation({
    mutationFn: markNotificationSeen,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs", "notifications"] });
      queryClient.invalidateQueries({ queryKey: ["jobs", "ranked"] });
    },
  });

  return (
    <SectionCard
      eyebrow="Opportunities"
      eyebrowColor="var(--section-jobs)"
      title="New matches"
      description="Jobs that clear your preferences and match threshold."
    >
      <ul className="space-y-3">
        {notifications.map((n) => (
          <li
            key={n.job.id}
            className="flex items-start justify-between gap-4 rounded-[var(--radius-input)] border p-3"
            style={{ borderColor: "var(--border)" }}
          >
            <div>
              <p className="text-sm font-medium">
                {n.job.designation}
                <span className="ml-2" style={{ color: "var(--fg-muted)" }}>
                  {n.job.company}
                </span>
              </p>
              {n.soft_preference_reasons.length > 0 && (
                <p className="mt-1 text-xs" style={{ color: "var(--fg-subtle)" }}>
                  {n.soft_preference_reasons.join(" · ")}
                </p>
              )}
            </div>
            <Button
              variant="secondary"
              disabled={markSeen.isPending}
              onClick={() => markSeen.mutate(n.job.id)}
            >
              Dismiss
            </Button>
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

/**
 * Proves the UI to sidecar path end to end. Kept visible on the dashboard
 * because a silently disconnected sidecar would otherwise look like an app
 * with no data, which is the single most confusing failure this architecture
 * allows.
 */
function SidecarStatus() {
  const { data, error, isPending } = useQuery({
    queryKey: ["status"],
    queryFn: getStatus,
  });

  return (
    <SectionCard
      eyebrow="Observe"
      eyebrowColor="var(--section-dashboard)"
      title="Local engine"
      description="Runs entirely on this machine."
    >
      {isPending ? (
        <StatusRow tone="var(--fg-muted)" label="Connecting" description="Waiting for the sidecar to respond." />
      ) : error ? (
        <StatusRow
          tone="var(--danger)"
          label="Unavailable"
          description={
            error instanceof SidecarUnavailableError
              ? error.message
              : `Request failed — ${(error as Error).message}`
          }
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <StatusRow tone="var(--success)" label="Connected" description={`v${data.version}`} />
          <StatusRow
            tone={data.database_ok ? "var(--success)" : "var(--warning)"}
            label={data.database_ok ? "Database ok" : "Database degraded"}
            description={`${data.table_count} tables`}
          />
        </div>
      )}
    </SectionCard>
  );
}

function StatusRow({
  tone,
  label,
  description,
}: {
  tone: string;
  label: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <span
        className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
        style={{ background: tone }}
        aria-hidden="true"
      />
      <div>
        <p className="text-sm font-semibold">{label}</p>
        <p className="selectable text-xs" style={{ color: "var(--fg-muted)" }}>
          {description}
        </p>
      </div>
    </div>
  );
}
