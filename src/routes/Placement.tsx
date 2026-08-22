import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Button, ErrorText } from "@/components/Form";
import { EmptyState, Page, SectionCard } from "@/components/Page";
import {
  confirmPlacementRecord,
  getPlacementStatus,
  getPlacementTimeline,
  GmailNotConnectedError,
  listPlacementReviewQueue,
  rejectPlacementRecord,
  syncPlacementMail,
} from "@/lib/api";
import type { PlacementRecordOut } from "@/lib/types";

export function Placement() {
  const { data: status } = useQuery({
    queryKey: ["placement", "status"],
    queryFn: getPlacementStatus,
  });

  if (status && !status.connected) {
    return (
      <Page title="Placement Timeline" description="Placement-cell communications, detected and organized.">
        <EmptyState
          title="Gmail not connected"
          hint="Connect Gmail to detect shortlists, interview announcements, and assessments, and to add confirmed events to your calendar."
          action={
            <Link
              to="/settings"
              className="btn"
              style={{ background: "var(--accent)", color: "var(--accent-fg)", borderColor: "var(--accent)" }}
            >
              Go to Settings
            </Link>
          }
        />
      </Page>
    );
  }

  return (
    <Page title="Placement Timeline" description="Placement-cell communications, detected and organized.">
      <SyncControl />
      <div className="mt-6">
        <ReviewQueue />
      </div>
      <div className="mt-6">
        <Timeline />
      </div>
    </Page>
  );
}

function SyncControl() {
  const queryClient = useQueryClient();
  const sync = useMutation({
    mutationFn: syncPlacementMail,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["placement"] });
    },
  });

  return (
    <div
      className="card flex items-center justify-between gap-4 rounded-[var(--radius-panel)] border p-4"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <p className="text-sm" style={{ color: "var(--fg-muted)" }}>
        Checks Gmail for new placement mail since the last sync.
      </p>
      <Button variant="primary" disabled={sync.isPending} onClick={() => sync.mutate()}>
        {sync.isPending ? "Syncing…" : "Sync now"}
      </Button>
      {sync.isError && (
        <ErrorText onDismiss={() => sync.reset()}>
          {sync.error instanceof GmailNotConnectedError
            ? "Gmail connection was lost -- reconnect it from Settings."
            : (sync.error as Error).message}
        </ErrorText>
      )}
    </div>
  );
}

/**
 * Anything below the auto-accept confidence (spec §7: "Produce a confidence
 * score for ambiguous matches") lands here rather than being silently
 * accepted or silently discarded -- a human confirms or rejects each one.
 */
function ReviewQueue() {
  const queryClient = useQueryClient();
  const { data: queue, isPending } = useQuery({
    queryKey: ["placement", "review-queue"],
    queryFn: listPlacementReviewQueue,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["placement", "review-queue"] });
    queryClient.invalidateQueries({ queryKey: ["placement", "timeline"] });
  };
  const confirm = useMutation({ mutationFn: confirmPlacementRecord, onSuccess: invalidate });
  const reject = useMutation({ mutationFn: rejectPlacementRecord, onSuccess: invalidate });

  if (isPending || !queue || queue.length === 0) return null;

  return (
    <SectionCard
      eyebrow="Needs review"
      eyebrowColor="var(--danger)"
      title="Unconfirmed matches"
      description="Below the auto-accept confidence -- confirm or reject each one."
    >
      <ul className="space-y-3">
        {queue.map((record) => (
          <li
            key={record.id}
            className="flex items-start justify-between gap-4 rounded-[var(--radius-input)] border p-3"
            style={{ borderColor: "var(--border)" }}
          >
            <div>
              <p className="text-sm font-medium">
                {record.company ?? "Unknown company"}
                <span
                  className="ml-2 rounded-[var(--radius-pill)] px-2 py-0.5 text-xs"
                  style={{ background: "var(--canvas-inset)", color: "var(--fg-subtle)" }}
                >
                  {record.status}
                </span>
              </p>
              <p className="mt-1 text-xs" style={{ color: "var(--fg-subtle)" }}>
                {record.source_document} · {Math.round(record.match_confidence * 100)}% confidence
                {record.matched_on.length > 0 && ` · matched on ${record.matched_on.join(", ")}`}
              </p>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button
                variant="secondary"
                disabled={reject.isPending}
                onClick={() => reject.mutate(record.id)}
              >
                Reject
              </Button>
              <Button
                variant="primary"
                disabled={confirm.isPending}
                onClick={() => confirm.mutate(record.id)}
              >
                Confirm
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

/** The spec's own company-progression view: Application -> Shortlisted ->
 * Assessment -> ... -> Offer, grouped per company. */
function Timeline() {
  const { data: timeline, isPending } = useQuery({
    queryKey: ["placement", "timeline"],
    queryFn: getPlacementTimeline,
  });

  const companies = timeline ? Object.entries(timeline) : [];

  if (isPending) return null;
  if (companies.length === 0) {
    return (
      <EmptyState
        title="No placement activity yet"
        hint="Sync will pick up shortlists, interview announcements, and results as they arrive."
      />
    );
  }

  return (
    <div className="space-y-4">
      {companies.map(([company, records]) => (
        <SectionCard key={company} eyebrow="Company" eyebrowColor="var(--section-placement)" title={company}>
          <TimelineRecords records={records} />
        </SectionCard>
      ))}
    </div>
  );
}

function TimelineRecords({ records }: { records: PlacementRecordOut[] }) {
  return (
    <ul className="space-y-3">
      {records.map((record) => (
        <li key={record.id} className="border-l-2 pl-3" style={{ borderColor: "var(--border-strong)" }}>
          <p className="text-sm font-medium">
            {record.status}
            {record.needs_review && (
              <span className="ml-2 text-xs" style={{ color: "var(--danger)" }}>
                needs review
              </span>
            )}
          </p>
          {record.events.map((event) => (
            <p key={event.id} className="mt-1 text-xs" style={{ color: "var(--fg-subtle)" }}>
              {event.event_type.replace("_", " ")}
              {event.event_date && ` · ${event.event_date}`}
              {event.start_time && ` at ${event.start_time}`}
              {event.venue && ` · ${event.venue}`}
              {event.calendar_event_id && " · on calendar"}
            </p>
          ))}
        </li>
      ))}
    </ul>
  );
}
