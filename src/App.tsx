import { createHashRouter, RouterProvider } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import {
  Career,
  Dashboard,
  Jobs,
  Outreach,
  Placement,
  Resumes,
  Settings,
  Tailor,
} from "@/routes";

// Hash routing, not browser routing: a packaged Tauri app serves from a custom
// protocol with no history fallback, so a path-based deep link would 404 on
// reload. The URL is never user-facing in a desktop shell.
const router = createHashRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "jobs", element: <Jobs /> },
      { path: "resumes", element: <Resumes /> },
      { path: "tailor", element: <Tailor /> },
      { path: "career", element: <Career /> },
      { path: "outreach", element: <Outreach /> },
      { path: "placement", element: <Placement /> },
      { path: "settings", element: <Settings /> },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
