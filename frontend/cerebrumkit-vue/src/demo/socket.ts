import { IS_DEMO } from './mode'

// The panel drives a chat over a WebSocket, and listens for four frame types:
// `typing`, `stop_typing`, `agent_loop_status` and `new_message`
// (see views/client/ProjectsView.vue). There is no server behind the demo, so
// this stands in for one: it accepts a sent message and answers with the same
// frames a real run would emit, in the same order.
//
// The reply does not pretend to be a model. A demo that fakes an answer is
// worse than one that explains itself, so it says what it is and then points at
// the parts of the panel that are real.

const AGENT_NAME = 'Support Agent'

const REPLY = [
  'This reply is canned: the hosted demo has the real panel but no model behind it.',
  '',
  'In a working install the loop would have: read this project\'s workflow, picked',
  'the Support Group, built a system prompt from those agents\' skills, called the',
  'model, executed whatever tools it asked for against the Python bodies stored in',
  'the tools table, and streamed the result back - as the typing and status frames',
  'you just saw.',
  '',
  'The rest of the panel is not canned. Open Tools to see a function spec and its',
  'Python body side by side, Storage for the orders table this project reads, and',
  'Projects for the canvas the two agents sit on.',
].join('\n')

type Frame = Record<string, unknown>

class DemoWebSocket extends EventTarget {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  readonly CONNECTING = 0
  readonly OPEN = 1
  readonly CLOSING = 2
  readonly CLOSED = 3
  readonly url: string
  readonly protocol = ''
  readonly extensions = ''
  readonly bufferedAmount = 0
  binaryType = 'blob'

  readyState = DemoWebSocket.CONNECTING

  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  private timers: ReturnType<typeof setTimeout>[] = []

  constructor(url: string | URL) {
    super()
    this.url = String(url)
    this.timers.push(
      setTimeout(() => {
        this.readyState = DemoWebSocket.OPEN
        const event = new Event('open')
        this.onopen?.(event)
        this.dispatchEvent(event)
      }, 30),
    )
  }

  private emit(frame: Frame) {
    const event = new MessageEvent('message', { data: JSON.stringify(frame) })
    this.onmessage?.(event)
    this.dispatchEvent(event)
  }

  private later(delay: number, run: () => void) {
    this.timers.push(setTimeout(run, delay))
  }

  send(raw: string) {
    let payload: { type?: string } = {}
    try {
      payload = JSON.parse(String(raw))
    } catch {
      return
    }
    if (payload.type !== 'message') {
      // `stop_agent_loop` and anything else: the loop is not running, so the
      // honest answer is that it has already stopped.
      this.emit({ type: 'agent_loop_status', status: 'idle' })
      return
    }

    this.emit({ type: 'agent_loop_status', status: 'running' })
    this.later(350, () => this.emit({ type: 'typing', user_name: AGENT_NAME }))
    this.later(1600, () => {
      this.emit({ type: 'stop_typing', user_name: AGENT_NAME })
      this.emit({
        type: 'new_message',
        message: {
          id: Date.now(),
          chat_id: this.chatId(),
          sender_type: 'agent',
          sender_id: 2,
          sender_name: AGENT_NAME,
          receiver_type: 'user',
          receiver_id: null,
          receiver_name: null,
          message_type: 'text',
          content: REPLY,
          created_at: new Date().toISOString(),
        },
      })
      this.emit({ type: 'agent_loop_status', status: 'idle' })
    })
  }

  private chatId(): number {
    const match = /\/ws\/chats\/(\d+)/.exec(this.url)
    return match ? Number(match[1]) : 0
  }

  close() {
    this.timers.forEach(clearTimeout)
    this.timers = []
    this.readyState = DemoWebSocket.CLOSED
    const event = new CloseEvent('close')
    this.onclose?.(event)
    this.dispatchEvent(event)
  }
}

/**
 * Replace the global WebSocket, so every `new WebSocket(...)` in the panel gets
 * the stand-in above without the views knowing.
 */
export function installDemoSocket(): void {
  if (!IS_DEMO) return
  ;(window as unknown as { WebSocket: unknown }).WebSocket = DemoWebSocket
}
