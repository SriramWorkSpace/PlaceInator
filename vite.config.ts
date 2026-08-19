import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Fixed dev port: the Tauri shell points its WebView here in development.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false,
  // Must mirror "paths" in tsconfig.json; a mismatch typechecks clean and then
  // fails at bundle time.
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 1420,
    strictPort: true,
  },
  build: {
    outDir: "dist-frontend",
    target: "chrome110", // WebView2 on Windows 10/11
    sourcemap: true,
  },
});
