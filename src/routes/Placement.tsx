import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "@/components/Badge";
import { Button, ErrorText } from "@/components/Form";
import { GroupsIcon } from "@/components/icons";
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
import type { BadgeTone } from "@/components/Badge";
import type { PlacementEventOut, PlacementRecordOut } from "@/lib/types";

/** PlacementStatus (placeinator/db/enums.py) is four flat outcomes, not a
 * progression -- "shortlisted"/"rejected" are terminal, "pending" and
 * "unknown" aren't. Maps each to the semantic Badge tone it actually means,
 * rather than every status reading as the same neutral gray. */
function statusTone(status: string): BadgeTone {
  switch (status) {
    case "shortlisted":
      return "success";
    case "rejected":
      return "danger";
    case "pending":
      return "warning";
    default:
      return "neutral";
  }
}

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
            ? "Gmail connection was lost. Reconnect it from Settings."
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
      description="Below the auto-accept confidence. Confirm or reject each one."
    >
      <ul className="space-y-3">
        {queue.map((record) => (
          <li
            key={record.id}
            className="flex items-start justify-between gap-4 rounded-[var(--radius-input)] border p-3"
            style={{ borderColor: "var(--border)" }}
          >
            <div>
              <p className="flex items-center gap-2 text-sm font-medium">
                <GroupsIcon width={14} height={14} style={{ color: "var(--section-placement)" }} />
                {record.company ?? "Unknown company"}
                <Badge tone={statusTone(record.status)}>{record.status}</Badge>
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

type EventStage = "done" | "current" | "future" | "undated";

/** Chronological order among this record's own events (nulls -- no date
 * extracted -- sort last, they're not part of the date-driven done/upcoming
 * read anyway). */
function sortByDate(events: PlacementEventOut[]): PlacementEventOut[] {
  return [...events].sort((a, b) => {
    if (!a.event_date && !b.event_date) return 0;
    if (!a.event_date) return 1;
    if (!b.event_date) return -1;
    return a.event_date.localeCompare(b.event_date);
  });
}

/** "current" is the first event today-or-later; everything before it is
 * "done", everything after is "future". An event with no extracted date
 * can't be placed on that axis, so it's its own state rather than a guess. */
function stageOf(event: PlacementEventOut, firstUpcomingId: number | null): EventStage {
  if (!event.event_date) return "undated";
  if (event.id === firstUpcomingId) return "current";
  const today = new Date().toISOString().slice(0, 10);
  return event.event_date < today ? "done" : "future";
}

const STAGE_STYLE: Record<EventStage, { dot: string; text: string }> = {
  done: { dot: "var(--success)", text: "var(--fg-muted)" },
  current: { dot: "var(--accent)", text: "var(--fg)" },
  future: { dot: "var(--canvas)", text: "var(--fg-muted)" },
  undated: { dot: "var(--canvas)", text: "var(--fg-subtle)" },
};

/** A real stepper over this record's own dated events -- there is no fixed
 * "Application -> Shortlisted -> ... -> Offer" sequence in the data model
 * (PlacementStatus is four flat outcomes, not stages; placeinator/db/enums.py),
 * so the honest progression to visualize is each record's actual events in
 * date order, not an invented stage list. */
function TimelineRecords({ records }: { records: PlacementRecordOut[] }) {
  return (
    <ul className="space-y-5">
      {records.map((record) => {
        const events = sortByDate(record.events);
        const today = new Date().toISOString().slice(0, 10);
        const firstUpcoming = events.find((e) => e.event_date && e.event_date >= today);
        return (
          <li key={record.id}>
            <p className="flex items-center text-sm font-medium">
              {record.status}
              {record.needs_review && (
                <span className="ml-2 text-xs" style={{ color: "var(--danger)" }}>
                  needs review
                </span>
              )}
            </p>
            {events.length === 0 ? (
              <p className="mt-1 text-xs" style={{ color: "var(--fg-subtle)" }}>
                No dated events yet.
              </p>
            ) : (
              <ol className="mt-2">
                {events.map((event, i) => {
                  const stage = stageOf(event, firstUpcoming?.id ?? null);
                  const style = STAGE_STYLE[stage];
                  const isLast = i === events.length - 1;
                  return (
                    <li key={event.id} className="relative flex gap-3 pb-4 last:pb-0">
                      {!isLast && (
                        <span
                          className="absolute top-3 left-[5px] w-px"
                          style={{ height: "calc(100% - 0.5rem)", background: "var(--border)" }}
                          aria-hidden="true"
                        />
                      )}
                      <span
                        className="relative z-10 mt-1 h-2.5 w-2.5 shrink-0 rounded-full border-2"
                        style={{
                          background: stage === "done" || stage === "current" ? style.dot : "var(--canvas)",
                          borderColor: stage === "future" || stage === "undated" ? "var(--border-strong)" : style.dot,
                        }}
                        aria-hidden="true"
                      />
                      <div>
                        <p className="text-sm font-medium" style={{ color: style.text }}>
                          {event.event_type.replace("_", " ")}
                          {stage === "current" && (
                            <span className="ml-2 text-xs font-normal" style={{ color: "var(--accent)" }}>
                              next
                            </span>
                          )}
                        </p>
                        <p className="mt-0.5 text-xs" style={{ color: "var(--fg-subtle)" }}>
                          {event.event_date ?? "date unknown"}
                          {event.start_time && ` at ${event.start_time}`}
                          {event.venue && ` · ${event.venue}`}
                          {event.calendar_event_id && " · on calendar"}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </li>
        );
      })}
    </ul>
  );
}
