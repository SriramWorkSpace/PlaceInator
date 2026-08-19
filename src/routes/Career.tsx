import { EmptyState, Page } from "@/components/Page";

export function Career() {
  return (
    <Page title="Skill Intelligence" description="Skill gaps between your profile and your target roles.">
      <EmptyState
        title="Not enough data yet"
        hint="Add resumes and target jobs first. Gaps are ranked by how often a skill appears across the roles you are aiming for."
      />
    </Page>
  );
}
