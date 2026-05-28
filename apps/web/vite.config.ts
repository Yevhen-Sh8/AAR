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
        runtimeCaching: [
          {
            urlPattern: /\/api\/.*/,
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
});
