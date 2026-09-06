import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    // `globals: true` expõe `afterEach` no escopo global — é disso que o
    // auto-cleanup do @testing-library/react depende para desmontar cada
    // componente renderizado entre testes (sem isso, renders de testes
    // anteriores continuam no DOM e produzem falsos positivos/negativos).
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
  resolve: {
    alias: {
      "@": path.resolve(dirname, "./src"),
    },
  },
});
