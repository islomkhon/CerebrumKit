// Origin of the FastAPI backend.
//
// This is configuration, not source. VITE_API_URL must be set (see .env.example)
// so a build can never quietly ship pointing at one particular machine, and the
// address never has to be edited in the code. Reading it in one place keeps
// REST and WebSocket callers on the same origin.
//
// The demo build is the one exception, and it is a build-time flag rather than
// a runtime one: `npm run build:demo` answers every request from a local
// snapshot (see src/demo), so it needs no origin at all.
import { IS_DEMO } from '../demo/mode'

const configured = import.meta.env.VITE_API_URL

if (!configured && !IS_DEMO) {
  throw new Error(
    'VITE_API_URL is not set. Copy .env.example to .env and point it at the backend origin.',
  )
}

// Never dialled in the demo build: the axios adapter and the WebSocket stub
// both answer before anything reaches the network, and this only has to be a
// syntactically valid origin.
const origin = configured || 'http://demo.invalid'

/** Origin including the scheme, e.g. `https://api.example.com`. */
export const API_BASE_URL: string = origin

/** The same origin without the scheme, for building `ws://` and `wss://` URLs. */
export const WS_BASE_URL: string = origin.replace(/^https?:\/\//, '')
