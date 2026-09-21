import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwind from "@tailwindcss/vite";

// Fixed port: Tauri's dev URL has to match, and a port that moves silently
// makes the shell load a blank window.
export default defineConfig({
  plugins: [react(), tailwind()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  build: { target: "es2022", outDir: "dist" },
});
