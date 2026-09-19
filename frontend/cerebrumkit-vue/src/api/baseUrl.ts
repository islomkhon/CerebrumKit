// Origin of the FastAPI backend.
//
// This is configuration, not source. VITE_API_URL must be set (see .env.example)
// so a build can never quietly ship pointing at one particular machine, and the
// address never has to be edited in the code. Reading it in one place keeps
// REST and WebSocket callers on the same origin.
const configured = import.meta.env.VITE_API_URL

if (!configured) {
  throw new Error(
    'VITE_API_URL is not set. Copy .env.example to .env and point it at the backend origin.',
  )
}

/** Origin including the scheme, e.g. `https://api.example.com`. */
export const API_BASE_URL: string = configured

/** The same origin without the scheme, for building `ws://` and `wss://` URLs. */
export const WS_BASE_URL: string = configured.replace(/^https?:\/\//, '')
