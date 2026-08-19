import { useQuery } from "@tanstack/react-query";

import { EmptyState, Page } from "@/components/Page";
import { getStatus, SidecarUnavailableError } from "@/lib/api";

export function Dashboard() {
  return (
    <Page title="Dashboard" description="Your placement activity at a glance.">
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
 * because a silently disconnected sidecar would otherwise look like an app with
 * no data, which is the single most confusing failure this architecture allows.
 */
function SidecarStatus() {
  const { data, error, isPending } = useQuery({
    queryKey: ["status"],
    queryFn: getStatus,
  });

  const state = isPending ? "connecting…" : error ? "unavailable" : "connected";
  const tone = isPending
    ? "var(--fg-muted)"
    : error
      ? "var(--danger)"
      : "var(--success)";

  return (
    <section
      className="rounded-md border p-4"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-medium">Local engine</h2>
        <span className="font-mono text-xs" style={{ color: tone }}>
          {state}
        </span>
      </div>

      {data && (
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 font-mono text-xs">
          <Row label="version">{data.version}</Row>
          <Row label="database">{data.database_ok ? "ok" : "degraded"}</Row>
          <Row label="tables">{String(data.table_count)}</Row>
        </dl>
      )}

      {error && (
        <p className="selectable mt-3 text-xs" style={{ color: "var(--danger)" }}>
          {error instanceof SidecarUnavailableError
            ? error.message
            : `Request failed — ${(error as Error).message}`}
        </p>
      )}
    </section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt style={{ color: "var(--fg-subtle)" }}>{label}</dt>
      <dd className="selectable">{children}</dd>
    </>
  );
}
