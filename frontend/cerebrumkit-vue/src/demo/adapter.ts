import type { AxiosAdapter, AxiosRequestConfig, AxiosResponse } from 'axios'
import fixtures from './fixtures.json'

// The panel is written against the REST API, and this answers it from a JSON
// snapshot of a seeded install instead. `backend/export_demo_fixtures.py` builds
// that snapshot from the application's own pydantic schemas, so the shapes here
// are the shapes the API returns and the same views, stores and components run
// as in a real install.
//
// Two deliberate choices:
//
// * A write is answered rather than refused. A demo that throws an error at
//   every button teaches a visitor nothing about the panel; this one accepts the
//   write, hands back something shaped like the answer, and simply does not
//   persist it. Reloading gives the original snapshot back.
// * An unknown GET returns an empty list rather than an error, so a screen this
//   snapshot has no data for renders empty instead of broken.

interface AnyRecord {
  [key: string]: any
}

interface Fixtures {
  user: AnyRecord
  users: AnyRecord[]
  projects: AnyRecord[]
  agents: AnyRecord[]
  skills: AnyRecord[]
  tools: AnyRecord[]
  platforms: AnyRecord[]
  project_agents: Record<string, number[]>
  project_users: Record<string, number[]>
  project_tables: Record<string, string[]>
  storage_tables: AnyRecord[]
  storage_rows: Record<string, AnyRecord[]>
  chats: AnyRecord[]
  chat_messages: Record<string, AnyRecord[]>
}

const F = fixtures as unknown as Fixtures

type Captures = RegExpMatchArray
type Handler = (m: Captures, params: AnyRecord, body: AnyRecord) => unknown

interface Route {
  method: string
  pattern: RegExp
  handler: Handler
}

/* ── Helpers ────────────────────────────────────────────────── */

function positive(value: unknown, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

/** The `*Page` shape: items plus the numbers the pager renders. */
function paginate(items: AnyRecord[], params: AnyRecord, sizeKey = 'page_size') {
  const page = positive(params?.page, 1)
  const size = positive(params?.[sizeKey], 20)
  return {
    items: items.slice((page - 1) * size, page * size),
    total: items.length,
    page,
    page_size: size,
    pages: Math.max(1, Math.ceil(items.length / size)),
  }
}

/** The storage shape, which spells the same idea differently. */
function rowPage(rows: AnyRecord[], params: AnyRecord) {
  const search = String(params?.search ?? '').trim().toLowerCase()
  const matched = search
    ? rows.filter((row) => JSON.stringify(row.data ?? {}).toLowerCase().includes(search))
    : rows
  const perPageRaw = params?.per_page
  const perPage = perPageRaw === 'all' ? Math.max(matched.length, 1) : positive(perPageRaw, 50)
  const page = positive(params?.page, 1)
  return {
    items: matched.slice((page - 1) * perPage, page * perPage),
    total: matched.length,
    page,
    per_page: perPage,
    pages: Math.max(1, Math.ceil(matched.length / perPage)),
  }
}

function findById(rows: AnyRecord[], id: string | undefined): AnyRecord | undefined {
  return rows.find((row) => String(row.id) === String(id))
}

function usersOf(projectId: string | undefined): AnyRecord[] {
  const ids = F.project_users[String(projectId)] ?? []
  return F.users.filter((user) => ids.includes(user.id))
}

function agentsOf(projectId: string | undefined): AnyRecord[] {
  const ids = F.project_agents[String(projectId)] ?? []
  return F.agents.filter((agent) => ids.includes(agent.id))
}

function tablesOf(projectId: string | undefined): AnyRecord[] {
  const names = F.project_tables[String(projectId)] ?? []
  return F.storage_tables.filter((table) => names.includes(table.name))
}

function messagePage(chatId: string | undefined) {
  const messages = F.chat_messages[String(chatId)] ?? []
  return { messages, has_more: false }
}

function chatsFor(predicate: (chat: AnyRecord) => boolean): AnyRecord[] {
  return F.chats.filter(predicate)
}

function chatsIn(project: AnyRecord): number {
  return F.chats.filter((chat) => String(chat.project_id) === String(project.id)).length
}

/**
 * Which account the demo signs in as.
 *
 * Any password is accepted. An address containing "client" gives the client
 * panel, anything else gives the admin panel, so both halves of the product are
 * reachable from one link without shipping two builds.
 */
function demoUser(email: unknown): AnyRecord {
  if (typeof email === 'string' && /client/i.test(email)) {
    return F.users.find((user) => user.role === 'client') ?? F.user
  }
  return F.user
}

/* ── Routes ─────────────────────────────────────────────────── */

const ROUTES: Route[] = [
  // Auth and accounts
  {
    method: 'post',
    pattern: /^\/auth\/login$/,
    handler: (_m, _params, body) => ({
      access_token: 'demo-snapshot-token',
      token_type: 'bearer',
      user: demoUser(body?.email),
    }),
  },
  { method: 'post', pattern: /^\/auth\/register$/, handler: (_m, _p, body) => ({ ...body, id: 900 }) },
  { method: 'get', pattern: /^\/auth\/users$/, handler: () => F.users },
  { method: 'get', pattern: /^\/admin\/users$/, handler: () => F.users },
  {
    method: 'get',
    pattern: /^\/admin\/users\/(\d+)$/,
    handler: (m) => findById(F.users, m[1]),
  },

  // Projects
  { method: 'get', pattern: /^\/admin\/projects$/, handler: () => F.projects },
  {
    method: 'get',
    pattern: /^\/admin\/projects\/(\d+)$/,
    handler: (m) => findById(F.projects, m[1]),
  },
  {
    method: 'get',
    pattern: /^\/admin\/projects\/(\d+)\/workflow$/,
    handler: (m) => findById(F.projects, m[1])?.workflow ?? { nodes: [], wires: [] },
  },
  {
    method: 'get',
    pattern: /^\/admin\/projects\/(\d+)\/agents$/,
    handler: (m, params) => paginate(agentsOf(m[1]), params),
  },
  {
    method: 'get',
    pattern: /^\/admin\/projects\/(\d+)\/available-agents$/,
    handler: (m, params) => {
      const taken = (F.project_agents[String(m[1])] ?? []).map(String)
      return paginate(F.agents.filter((agent) => !taken.includes(String(agent.id))), params)
    },
  },
  {
    method: 'get',
    pattern: /^\/admin\/projects\/(\d+)\/users$/,
    handler: (m, params) => paginate(usersOf(m[1]), params),
  },
  {
    method: 'get',
    pattern: /^\/admin\/projects\/(\d+)\/available-users$/,
    handler: (m, params) => {
      const taken = (F.project_users[String(m[1])] ?? []).map(String)
      return paginate(F.users.filter((user) => !taken.includes(String(user.id))), params)
    },
  },
  {
    method: 'get',
    pattern: /^\/admin\/projects\/(\d+)\/tables$/,
    handler: (m, params) => paginate(tablesOf(m[1]), params),
  },
  {
    method: 'get',
    pattern: /^\/admin\/projects\/(\d+)\/available-tables$/,
    handler: (m, params) => {
      const taken = F.project_tables[String(m[1])] ?? []
      return paginate(F.storage_tables.filter((t) => !taken.includes(t.name)), params)
    },
  },

  // Admin view of a user's chats
  {
    method: 'get',
    pattern: /^\/admin\/projects\/(\d+)\/users\/(\d+)\/chats$/,
    handler: (m) =>
      chatsFor((chat) => String(chat.project_id) === m[1] && String(chat.user_id) === m[2]),
  },
  {
    method: 'get',
    pattern: /^\/admin\/projects\/\d+\/users\/\d+\/chats\/(\d+)\/messages$/,
    handler: (m) => messagePage(m[1]),
  },

  // Agents, skills, tools
  { method: 'get', pattern: /^\/admin\/agents$/, handler: () => F.agents },
  { method: 'get', pattern: /^\/admin\/agents\/(\d+)$/, handler: (m) => findById(F.agents, m[1]) },
  {
    method: 'get',
    pattern: /^\/admin\/agents\/(\d+)\/skills$/,
    handler: (m) => {
      const ids = findById(F.agents, m[1])?.skill_ids ?? []
      return F.skills.filter((skill) => ids.includes(skill.id))
    },
  },
  { method: 'get', pattern: /^\/admin\/skills$/, handler: () => F.skills },
  { method: 'get', pattern: /^\/admin\/tools$/, handler: () => F.tools },

  // Storage library
  { method: 'get', pattern: /^\/admin\/storage\/tables$/, handler: () => F.storage_tables },
  {
    method: 'get',
    pattern: /^\/admin\/storage\/tables\/([^/]+)\/rows$/,
    handler: (m, params) => rowPage(F.storage_rows[decodeURIComponent(m[1])] ?? [], params),
  },

  // LLM connections
  { method: 'get', pattern: /^\/admin\/platforms$/, handler: () => F.platforms },

  // Client panel
  {
    method: 'get',
    pattern: /^\/client\/projects$/,
    handler: () =>
      // Projects that hold a conversation come first. The client panel opens on
      // the first project in this list, and the System project has no chats:
      // landing there shows an empty list beside an empty pane, which reads as
      // a broken demo rather than an empty one.
      [...F.projects]
        .filter((project) => project.is_active)
        .sort((a, b) => chatsIn(b) - chatsIn(a)),
  },
  {
    method: 'get',
    pattern: /^\/client\/projects\/(\d+)\/chats$/,
    handler: (m) => chatsFor((chat) => String(chat.project_id) === m[1]),
  },
  {
    method: 'get',
    pattern: /^\/client\/projects\/\d+\/chats\/(\d+)\/messages$/,
    handler: (m) => messagePage(m[1]),
  },
]

/* ── The adapter ────────────────────────────────────────────── */

function respond(config: AxiosRequestConfig, data: unknown): AxiosResponse {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: config as never,
  }
}

function parseBody(data: unknown): AnyRecord {
  if (!data) return {}
  if (typeof data === 'string') {
    try {
      return JSON.parse(data)
    } catch {
      return {}
    }
  }
  return data as AnyRecord
}

export const demoAdapter: AxiosAdapter = async (config) => {
  const method = (config.method ?? 'get').toLowerCase()
  const path = String(config.url ?? '')
    .replace(/^https?:\/\/[^/]+/, '')
    .split('?')[0]
  const params = (config.params ?? {}) as AnyRecord
  const body = parseBody(config.data)

  const route = ROUTES.find((entry) => entry.method === method && entry.pattern.test(path))
  if (route) {
    const captures = path.match(route.pattern) as Captures
    return respond(config, route.handler(captures, params, body))
  }

  // A write this snapshot has no rule for: accept it, echo it back with an id,
  // and let the panel behave as though it worked. Nothing is persisted.
  if (method !== 'get') {
    return respond(config, method === 'delete' ? {} : { ...body, id: Date.now() % 100000 })
  }

  return respond(config, [])
}
