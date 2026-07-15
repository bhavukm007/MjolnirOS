import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 750,
    rollupOptions: {
      output: {
        manualChunks: {
          "core-effects": ["@react-three/postprocessing", "postprocessing"],
          "core-fiber": ["@react-three/fiber"],
          "core-three": ["three"]
        }
      }
    }
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.js"
  }
});
