import { EmptyState, Page } from "@/components/Page";

export function Tailor() {
  return (
    <Page title="Tailor" description="Restructure a LaTeX resume for a specific job description.">
      <EmptyState
        title="Nothing to tailor yet"
        hint="Provide a job description and a .tex resume. Content is reordered, selected, and emphasized — never rewritten, and nothing is ever invented."
      />
    </Page>
  );
}
