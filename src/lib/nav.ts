/** Left-hand navigation, in the order given at specification.md lines 812-826. */
export interface NavItem {
  path: string;
  label: string;
}

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Dashboard" },
  { path: "/jobs", label: "Jobs" },
  { path: "/resumes", label: "Resumes" },
  { path: "/tailor", label: "Tailor" },
  { path: "/career", label: "Career" },
  { path: "/outreach", label: "Outreach" },
  { path: "/placement", label: "Placement" },
];

export const SETTINGS_ITEM: NavItem = { path: "/settings", label: "Settings" };
