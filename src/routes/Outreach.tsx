import { EmptyState, Page } from "@/components/Page";

export function Outreach() {
  return (
    <Page title="Outreach" description="Personalized cold-mail drafts.">
      <EmptyState
        title="No drafts yet"
        hint="Drafts are built from your profile and a specific opportunity. You review and send every message yourself."
      />
    </Page>
  );
}
