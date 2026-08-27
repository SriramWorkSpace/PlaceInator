import { useQuery } from "@tanstack/react-query";
import { createHashRouter, RouterProvider } from "react-router-dom";

import logo from "@/assets/logo.png";
import { AppShell } from "@/components/AppShell";
import { TitleBar } from "@/components/TitleBar";
import { getProfile, NotOnboardedError } from "@/lib/api";
import {
  Career,
  Dashboard,
  Jobs,
  Outreach,
  Placement,
  Profile,
  Resumes,
  Settings,
  Tailor,
} from "@/routes";
import { Onboarding } from "@/routes/Onboarding";

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
      { path: "profile", element: <Profile /> },
      { path: "settings", element: <Settings /> },
    ],
  },
]);

/**
 * Gates the whole app on whether a profile exists yet -- a fresh install (or
 * a fresh data dir) 404s from GET /api/profile, which getProfile turns into
 * NotOnboardedError. That state gets Onboarding's full-screen greeting
 * instead of the normal sidebar shell; every other query error (sidecar
 * still starting, a real network failure) falls through to the router
 * unchanged, since individual pages (Dashboard's SidecarStatus, etc.)
 * already handle those themselves.
 *
 * Reusing queryKey ["profile"] here is deliberate: it's the same cache entry
 * AppShell's ProfileLink and the Profile route already read, so this adds no
 * extra request, and Onboarding's own final step invalidates the very same
 * key to hand control back to the router with no reload.
 */
export function App() {
  const { data, error, isPending } = useQuery({
    queryKey: ["profile"],
    queryFn: getProfile,
    retry: (count, err) => !(err instanceof NotOnboardedError) && count < 2,
  });

  return (
    <div className="flex h-full flex-col">
      <TitleBar />
      <div className="h-full min-h-0 flex-1">
        {isPending ? (
          <Splash />
        ) : !data && error instanceof NotOnboardedError ? (
          <Onboarding />
        ) : (
          <RouterProvider router={router} />
        )}
      </div>
    </div>
  );
}

/** The very first frame a launch renders -- a branded pause rather than a
 * blank flash while the profile check above settles. */
function Splash() {
  return (
    <div className="flex h-full items-center justify-center" style={{ background: "var(--canvas)" }}>
      <img src={logo} alt="" className="h-10 w-10 animate-pulse" aria-hidden="true" />
    </div>
  );
}
