import { EmptyState, Page } from "@/components/Page";

export function Jobs() {
  return (
    <Page title="Jobs" description="Ranked opportunities matched against your resumes.">
      <EmptyState
        title="No jobs yet"
        hint="Paste a job description or URL to add one manually. Automatic discovery from job boards arrives in M2."
      />
    </Page>
  );
}
