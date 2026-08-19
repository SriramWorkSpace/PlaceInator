import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A local sidecar does not change behind our back; refetching on window
      // focus is pure noise here.
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});
