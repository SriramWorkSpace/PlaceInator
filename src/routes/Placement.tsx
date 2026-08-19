import { EmptyState, Page } from "@/components/Page";

export function Placement() {
  return (
    <Page title="Placement Timeline" description="Placement-cell communications, detected and organized.">
      <EmptyState
        title="Gmail not connected"
        hint="Connect Gmail to detect shortlists, interview announcements, and assessments, and to add confirmed events to your calendar."
      />
    </Page>
  );
}
