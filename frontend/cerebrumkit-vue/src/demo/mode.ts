// Demo mode is a build-time switch, not a runtime one.
//
// `npm run build:demo` sets VITE_DEMO=1. The bundle it produces answers the
// panel from the JSON snapshot beside this file instead of from a FastAPI
// backend, so it can be served as plain files - which is what the hosted demo
// on GitHub Pages is. A normal build never sets the flag, so none of this is
// reachable in a real deployment and no query string or setting can turn it on.
export const IS_DEMO: boolean = import.meta.env.VITE_DEMO === '1'
