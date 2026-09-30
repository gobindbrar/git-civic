import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/",
  plugins: [react()],
  build: {
    outDir: path.resolve(import.meta.dirname, "static/auth-dist"),
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(import.meta.dirname, "auth-entry.tsx"),
      output: { entryFileNames: "auth.js", assetFileNames: "[name][extname]" },
    },
  },
});