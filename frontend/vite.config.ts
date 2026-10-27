/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build goes into the Django app's static folder: Django serves it at /dashboard/ (login required) and its
// assets under /static/dashboard/. In development, `npm run dev` forwards the API and the login to Django (:8000).
export default defineConfig({
  plugins: [react()],
  base: "/static/dashboard/",
  build: {
    outDir: "../src/apps/dashboard/static/dashboard",
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 700, // React + Recharts in one file (~180 kB gzip): one page, no need to split it
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/accounts": "http://127.0.0.1:8000",
      "/static/dashboard-login": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
  },
});
