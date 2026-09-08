import { defineConfig, loadEnv } from "vite";

import react from "@vitejs/plugin-react";

import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  // ==========================================================
  // Environment Configuration
  // ==========================================================
  //
  // Load VITE_* variables from the frontend environment files.
  //
  // Using "." avoids requiring Node.js type definitions solely
  // for process.cwd(). The Vite project root is the current
  // frontend directory.
  // ==========================================================

  const env = loadEnv(mode, ".", "VITE_");

  return {
    // ========================================================
    // Vite Plugins
    // ========================================================

    plugins: [react(), tailwindcss()],

    // ========================================================
    // Development Server
    // ========================================================

    server: {
      // Frontend development server port.
      port: 5173,

      // Allow the development server to be accessed from
      // other devices on the network, including devices
      // reaching it through ngrok.
      host: true,

      // Allow the configured public frontend hostname.
      //
      // VITE_FRONTEND_HOST is defined in frontend/.env.
      //
      // IMPORTANT:
      // The value must contain only the hostname, without
      // http:// or https://.
      allowedHosts: env.VITE_FRONTEND_HOST ? [env.VITE_FRONTEND_HOST] : [],
    },
  };
});
