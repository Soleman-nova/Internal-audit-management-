import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    // Fail loudly instead of quietly moving to the next free port.
    //
    // The Logto redirect URI is derived from `window.location.origin` on purpose —
    // the SDK stores the PKCE verifier in the *initiating* origin's storage, so
    // hardcoding an origin breaks the exchange when the app is opened anywhere else.
    // That makes the port part of the OAuth configuration: every port the app is
    // served on must be registered in Logto Console, matched exactly.
    //
    // Vite's default is to fall forward to 5174, 5175, … when the port is taken,
    // which silently produces an origin Logto does not recognise. The symptom is a
    // 400 from Logto's /oidc/auth endpoint, which reads as a broken server rather
    // than as "you are on the wrong port". Refusing to start says so directly.
    //
    // To legitimately use another port, change it here *and* register
    // `http://localhost:<port>/callback` plus the matching post-sign-out URI.
    strictPort: true,
  },
})
