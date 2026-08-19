import { useQuery } from "@tanstack/react-query";

import { EmptyState, Page, SectionCard } from "@/components/Page";
import { getStatus, SidecarUnavailableError } from "@/lib/api";

export function Dashboard() {
  return (
    <Page
      title="Studio Overview"
      description="Your placement activity at a glance -- profile, resumes, jobs, and the local engine that ties them together."
    >
      <SidecarStatus />
      <div className="mt-6">
        <EmptyState
          title="Nothing to show yet"
          hint="Complete onboarding and add a resume to start seeing matched opportunities and upcoming placement events here."
        />
      </div>
    </Page>
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
