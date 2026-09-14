import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { apiProxy } from "./vite.api-proxy";

export default defineConfig({
  plugins: [react(), apiProxy()],
  server: { port: 5201 },
});
