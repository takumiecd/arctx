import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During `npm run dev`, proxy API calls to a locally-running `arctx serve`
// (default port 8787) so the frontend and backend can run on separate ports
// without CORS friction. Override with VITE_ARCTX_API.
const apiTarget = process.env.VITE_ARCTX_API ?? "http://127.0.0.1:8787";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Anchor exact API paths so the prefix "/node" does NOT swallow Vite's
      // own "/node_modules/..." requests (which otherwise 404 via the proxy).
      "^/run$": apiTarget,
      "^/node$": apiTarget,
      "^/step$": apiTarget,
      "^/attach$": apiTarget,
      "^/cut$": apiTarget,
      "^/lane$": apiTarget,
      "^/lane/adopt$": apiTarget,
      "^/ext(/.*)?$": apiTarget,
      "^/health$": apiTarget,
      "^/web(/.*)?$": apiTarget,
      "^/artifacts(/.*)?$": apiTarget,
    },
  },
});
