import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// The page is built into the Python package, so it travels with Shire and
// nobody who installs it needs Node.js.
export default defineConfig({
  plugins: [vue()],
  build: { outDir: "../src/shire/page", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:5190" } },
  test: { environment: "jsdom", include: ["tests/**/*.test.ts"] },
});
