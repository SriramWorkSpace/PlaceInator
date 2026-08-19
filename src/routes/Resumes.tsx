import { EmptyState, Page } from "@/components/Page";

export function Resumes() {
  return (
    <Page title="Resumes" description="Your role-specific resume library.">
      <EmptyState
        title="No resumes yet"
        hint="Upload a PDF, DOCX, or LaTeX resume. Each one is parsed into skills, projects, and experience so jobs can be matched against all of them."
      />
    </Page>
  );
}
