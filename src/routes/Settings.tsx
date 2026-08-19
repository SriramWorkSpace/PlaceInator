import { EmptyState, Page } from "@/components/Page";

export function Settings() {
  return (
    <Page title="Settings" description="Profile, preferences, and integrations.">
      <EmptyState
        title="Onboarding not complete"
        hint="Your profile, career preferences, and employment constraints will be editable here once onboarding lands in M1."
      />
    </Page>
  );
}
