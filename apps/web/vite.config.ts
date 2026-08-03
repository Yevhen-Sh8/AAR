import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  base: process.env.VITE_BASE ?? "/",
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "AAR — After Action Review",
        short_name: "AAR",
        description: "Цифрова платформа аналізу та накопичення досвіду",
        theme_color: "#1a3a1a",
        background_color: "#0a1a0a",
        display: "standalone",
        lang: "uk",
        icons: [],
      },
      workbox: {
        navigateFallback: "/index.html",
        // Never serve the SPA shell for API paths — the backend may live on a
        // different origin (split-host prod), and POST/PATCH must reach it raw.
        navigateFallbackDenylist: [/^\/api\//, /\/api\//],
        runtimeCaching: [
          {
            // Only cache *same-origin GET* reads. Cross-origin API (a separate
            // split-host) and all mutations bypass the service worker entirely,
            // which avoids opaque "string did not match the expected pattern"
            // fetch failures on iOS/Safari PWAs.
            urlPattern: ({ url, request, sameOrigin }) =>
              sameOrigin && request.method === "GET" && url.pathname.startsWith("/api/"),
            handler: "NetworkFirst",
            options: {
              cacheName: "api-cache",
              networkTimeoutSeconds: 5,
            },
          },
        ],
      },
    }),
  ],
  test: {
    environment: "jsdom",
    globals: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Split rarely-changing vendor deps into their own cacheable chunks,
        // separate from route chunks created by the React.lazy() calls in
        // App.tsx. Keeps the initial (login-only) bundle small.
        manualChunks: {
          vendor_react: ["react", "react-dom", "react-router-dom"],
          vendor_query: ["@tanstack/react-query"],
          vendor_charts: ["recharts"],
          vendor_icons: ["lucide-react"],
        },
      },
    },
  },
});
