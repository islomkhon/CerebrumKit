import fixtures from './fixtures.json'
import { IS_DEMO } from './mode'
import { installDemoSocket } from './socket'

export { IS_DEMO }

interface SnapshotUser {
  role: string
}

/**
 * Put the demo into the state the panel expects to find after a sign-in.
 *
 * The auth store reads `token` and `user` straight out of local storage, and
 * the router guard decides which half of the panel a visitor may see from
 * `user.role`. Seeding both before the app mounts is therefore enough to land
 * on the admin panel with no sign-in step, while leaving the sign-in form
 * working - type any address, and one containing "client" opens the client
 * panel instead (see the login route in adapter.ts).
 *
 * Must run before `app.mount`, and before anything constructs a WebSocket.
 */
export function installDemoRuntime(): void {
  if (!IS_DEMO) return

  const user = (fixtures as unknown as { user: SnapshotUser }).user
  localStorage.setItem('token', 'demo-snapshot-token')
  localStorage.setItem('user', JSON.stringify(user))

  installDemoSocket()
}
