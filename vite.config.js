import { defineConfig } from "vite";

// The app lives in web/; `npm run build` writes a self-contained static site
// to dist/ (relative asset paths so it works from any sub-path, e.g. GitHub Pages).
export default defineConfig({
  root: "web",
  base: "./",
  publicDir: "public",
  build: { outDir: "../dist", emptyOutDir: true },
  server: { port: 5173, open: false },
});
