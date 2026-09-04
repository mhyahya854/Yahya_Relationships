import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendTarget = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: false,
      },
    },
  },
  build: {
    target: "es2020",
    outDir: "dist",
    chunkSizeWarningLimit: 4000,
    rollupOptions: {
      output: {
        manualChunks: {
          mermaid: ["mermaid"],
        },
      },
    },
  },
});
