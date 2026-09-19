<script setup lang="ts">
// @ts-nocheck
import { ref, onMounted, onUnmounted, nextTick, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../../stores/auth'
import { fetchProjects, createProject } from '../../api/projects'
import { fetchUsers } from '../../api/users'
import { fetchAdminUserChats, createAdminChat, fetchAdminChatMessages, sendAdminChatMessage } from '../../api/chats'
import { generateJson } from '../../api/generator'
import api from '../../api/client'
import { fetchRows, createRow, updateRow, deleteRow, exportExcel, importExcel, previewExcel, updateTable } from '../../api/storage'
import type { ExcelPreview } from '../../api/storage'
import type { Project, User, Agent, AgentContextTool, Chat, Message, Skill, StorageTableInfo, StorageRow, StorageColumnInfo, StorageTableUpdate } from '../../types'
import { renderMarkdown } from '../../utils/markdown'
import { WS_BASE_URL } from '../../api/baseUrl'

const dataTypes = [
  'integer', 'bigInteger', 'smallInteger', 'tinyInteger',
  'string', 'text', 'longText', 'mediumText',
  'boolean', 'float', 'double', 'decimal',
  'date', 'dateTime', 'time', 'timestamp',
  'json', 'jsonb',
]

type ProjectModalColumn = {
  name: string
  data_type: string
  description: string
  length: number | null
  nullable: boolean
  default_value: any
}

const { t } = useI18n()
const authStore = useAuthStore()
const currentUser = computed(() => authStore.user)

// ── Projects ──
const projects = ref<Project[]>([])
const selectedProjectId = ref<number | null>(null)
const loadingProjects = ref(false)
const projectSearch = ref('')

const filteredProjects = computed(() => {
  if (!projectSearch.value) return projects.value
  const q = projectSearch.value.toLowerCase()
  return projects.value.filter(p => p.name.toLowerCase().includes(q) || (p.description && p.description.toLowerCase().includes(q)))
})

// ── Project modal ──
const showProjectModal = ref(false)
const editingId = ref<number | null>(null)
const projectForm = ref({ name: '', description: '', is_active: true })

// ── Agents ──
const PROJECT_MEMBERS_PAGE_SIZE = 10

const projectAgents = ref<Agent[]>([])
const agentSearch = ref('')
const loadingAgents = ref(false)
const agentPage = ref(1)
const agentPages = ref(1)
const agentTotal = ref(0)
const activeSkills = ref<Skill[]>([])
const generatingAgent = ref(false)

const showAgentEditModal = ref(false)
const editAgentId = ref<number | null>(null)
const editAgentName = ref('')
const editAgentDescription = ref('')
const editAgentIsActive = ref(true)
const editAgentSkillIds = ref<number[]>([])
const editAgentGeneratorPrompt = ref('')
const editAgentContextTools = ref<AgentContextTool[]>([])
const editContextToolToAdd = ref<number | null>(null)

const showCreateAgentModal = ref(false)
const createAgentName = ref('')
const createAgentDescription = ref('')
const createAgentSkillIds = ref<number[]>([])
const createAgentGeneratorPrompt = ref('')
const createAgentContextTools = ref<AgentContextTool[]>([])
const createContextToolToAdd = ref<number | null>(null)

// ── Add member modal ──
const showAddAgentModal = ref(false)
const showAddUserModal = ref(false)
const showAddTableModal = ref(false)
const memberSearch = ref('')
const availableMembers = ref<any[]>([])
const loadingAvailable = ref(false)
const memberPage = ref(1)
const memberPages = ref(1)
const memberTotal = ref(0)

// ── Users ──
const projectUsers = ref<User[]>([])
const userSearch = ref('')
const loadingUsers = ref(false)
const selectedUserId = ref<number | null>(null)
const userPage = ref(1)
const userPages = ref(1)
const userTotal = ref(0)

// ── Tables ──
const projectTables = ref<StorageTableInfo[]>([])
const tableSearch = ref('')
const loadingTables = ref(false)
const tablePage = ref(1)
const tablePages = ref(1)
const tableTotal = ref(0)
const selectedProjectTable = ref<string | null>(null)
const tableDataRows = ref<StorageRow[]>([])
const tableDataPage = ref(1)
const tableDataPages = ref(1)
const tableDataTotal = ref(0)
const tableDataSearch = ref('')
const tableDataSortBy = ref('id')
const tableDataSortDir = ref<'asc' | 'desc'>('asc')
const loadingTableData = ref(false)
const selectedTableDataRowIds = ref<number[]>([])
const tableNotice = ref('')
const tableDataError = ref('')
const showProjectRowModal = ref(false)
const editingProjectRowId = ref<number | null>(null)
const projectRowData = ref<Record<string, any>>({})
const projectRowSaving = ref(false)
const projectRowError = ref('')
const showProjectImportModal = ref(false)
const excelFile = ref<File | null>(null)
const excelPreview = ref<ExcelPreview | null>(null)
const importMapping = ref<Record<string, string>>({})
const previewingExcel = ref(false)
const importing = ref(false)
const showProjectTableModal = ref(false)
const editingProjectTableName = ref<string | null>(null)
const projectTableName = ref('')
const projectTableDescription = ref('')
const projectModalColumns = ref<ProjectModalColumn[]>([])
const projectTableSaving = ref(false)
const projectTableError = ref('')

// ── Chats ──
const userChats = ref<Chat[]>([])
const userChatSearch = ref('')
const loadingChats = ref(false)
const selectedChatId = ref<number | null>(null)
const selectedChatDescription = ref('')

const selectedChat = computed(() => userChats.value.find(c => c.id === selectedChatId.value) || null)

// Phone navigation: below 768px the five columns are shown one at a time, so a
// tap moves on to the next pane instead of widening the row and the step bar
// carries the way back. The loaders also pick the first user and chat on their
// own; those calls pass `auto` so a phone keeps the pane the tap asked for.
type MobilePane = 'projects' | 'project' | 'workflow' | 'data' | 'chats' | 'chat'
const mobilePane = ref<MobilePane>('projects')
const isProjectPane = computed(() => (
  mobilePane.value === 'project' || mobilePane.value === 'workflow' || mobilePane.value === 'data'
))
const mobileBackLabel = computed(() => {
  if (mobilePane.value === 'chat') return t('admin.chat.title')
  if (mobilePane.value === 'chats') return t('admin.sidebar.users')
  return t('admin.sidebar.projects')
})

function mobileBack() {
  if (mobilePane.value === 'chat') {
    selectedChatId.value = null
    mobilePane.value = 'chats'
    return
  }
  if (mobilePane.value === 'chats') {
    selectedUserId.value = null
    selectedChatId.value = null
    mobilePane.value = 'project'
    return
  }
  selectedProjectId.value = null
  selectedUserId.value = null
  selectedChatId.value = null
  mobilePane.value = 'projects'
}

const showCreateChatModal = ref(false)
const createChatDescription = ref('')

const showChatModal = ref(false)
const chatForm = ref({ description: '' })
const editingChatId = ref<number | null>(null)

// ── Messages ──
const messages = ref<Message[]>([])
const newMessageContent = ref('')
const sending = ref(false)
const chatLoading = ref(false)
const clickedChatId = ref<number | null>(null)
const loadingMessages = ref(false)
const typingUser = ref<string | null>(null)
const agentLoopRunning = ref(false)
const agentLoopStopping = ref(false)
// The switch outlives a reload: it used to reset to off, which meant
// re-finding the chat and the run being inspected. Kept per browser, the
// way the sidebar keeps its collapsed state.
const DEBUG_MODE_KEY = 'admin_chat_debug_mode'
const debugMode = ref(localStorage.getItem(DEBUG_MODE_KEY) === 'true')
watch(debugMode, (enabled) => localStorage.setItem(DEBUG_MODE_KEY, String(enabled)))
let typingTimer: ReturnType<typeof setTimeout> | null = null

// Debug mode off: the conversation as one of its participants sees it — the
// selected user's messages to the agent, the agent's replies, and anything the
// admin added to this chat themselves.
// Debug mode on: show every message (agents, tools, etc.).
const visibleMessages = computed(() => messages.value.filter(isVisibleMessage))

// Kept as its own function because the pager asks the same question while it
// loads: a page can be nothing but rows this test rejects, and then it would
// render as an empty chat.
function isVisibleMessage(msg: Message) {
  if (debugMode.value) return true
  // The chat belongs to the selected user, so the conversation has to be
  // filtered by *their* id as well. Filtering by the signed-in admin alone hid
  // every message of another user's chat until debug mode was switched on.
  const participants = [currentUser.value?.id, selectedUserId.value]
  // Internal "flow" rows (how the input passed between agents) and "tool" rows
  // (tool input/output) never belong in the normal view.
  return (
    msg.message_type !== 'flow' &&
    msg.message_type !== 'tool' &&
    (participants.includes(msg.sender_id) || participants.includes(msg.receiver_id))
  )
}

function debugTypeClass(type) {
  if (!type) return 'is-null'
  const t = String(type).toLowerCase()
  if (t.includes('user')) return 'is-user'
  if (t.includes('agent')) return 'is-agent'
  if (t.includes('tool')) return 'is-tool'
  return 'is-other'
}

// The bubble tint encodes the hop the message took, so the shape of a run is
// readable at a glance: a person talking to an agent, a tool reporting back to
// the agent that called it, an agent answering a person, or one agent handing
// its output to the next. Alignment and the bubble tail still come from
// chat-bubble-mine / chat-bubble-other; this only picks the surface.
function bubbleTone(msg: Message) {
  if (msg.message_type === 'tool') return 'chat-bubble-tool-to-agent'
  if (msg.sender_type === 'user') return 'chat-bubble-user-to-agent'
  if (msg.receiver_type === 'user') return 'chat-bubble-agent-to-user'
  return 'chat-bubble-agent-to-agent'
}

// Consecutive messages from one sender form a run. The run prints the sender
// name once, on its first bubble, and stacks its bubbles closer together.
// Debug cards open on demand: an expanded card is roughly three times taller
// than the collapsed summary, so keeping them shut is what makes debug mode
// scannable when a chat has dozens of tool messages.
const expandedDebugIds = ref<number[]>([])

function isDebugExpanded(id: number) {
  return expandedDebugIds.value.includes(id)
}

function toggleDebugDetails(id: number) {
  expandedDebugIds.value = isDebugExpanded(id)
    ? expandedDebugIds.value.filter((item) => item !== id)
    : [...expandedDebugIds.value, id]
}

function continuesPreviousRun(index: number) {
  const msg = visibleMessages.value[index]
  const previous = visibleMessages.value[index - 1]
  if (!msg || !previous) return false
  const sameDay = new Date(previous.created_at).toDateString() === new Date(msg.created_at).toDateString()
  return sameDay && previous.sender_id === msg.sender_id && previous.sender_name === msg.sender_name
}

// A bubble belongs on the right only when the viewer is the one who wrote it.
// The id alone cannot decide that: a tool card carries its tool's id in
// sender_id (see the tool-message save in agent_loop), and tool ids share one
// number space with user ids - memory_write is tool 26, the admin is user 26 -
// so the card was read as "mine". Requiring sender_type 'user' keeps them apart.
function isOwnMessage(msg: Message) {
  return msg.sender_type === 'user' && msg.sender_id === currentUser.value?.id
}

// Repeating the sender above every bubble was noise, not information.
function showSender(index: number) {
  if (debugMode.value) return false
  const msg = visibleMessages.value[index]
  if (!msg || isOwnMessage(msg)) return false
  return !continuesPreviousRun(index)
}

function isGroupedWithPrevious(index: number) {
  if (debugMode.value) return false
  return continuesPreviousRun(index)
}

// Markdown tables carry a copy chip: the table is turned back into markdown so
// it can be pasted into a chat, an issue or a document unchanged.
function tableToMarkdown(table: HTMLTableElement) {
  const rows = Array.from(table.querySelectorAll('tr'))
    .map((row) =>
      Array.from(row.querySelectorAll('th, td')).map((cell) =>
        (cell.textContent || '').replace(/\|/g, '\\|').replace(/\s*\n\s*/g, ' ').trim(),
      ),
    )
    .filter((row) => row.length)
  if (!rows.length) return ''

  const columns = Math.max(...rows.map((row) => row.length))
  const toLine = (row: string[]) =>
    `| ${Array.from({ length: columns }, (_, index) => row[index] ?? '').join(' | ')} |`
  const [header, ...body] = rows
  const separator = `| ${Array.from({ length: columns }, () => '---').join(' | ')} |`
  return [toLine(header), separator, ...body.map(toLine)].join('\n')
}

async function onMessagesClick(event: MouseEvent) {
  const button = (event.target as HTMLElement)?.closest('.md-copy-btn') as HTMLButtonElement | null
  if (!button) return

  const table = button.closest('.md-table-wrap')?.querySelector('table')
  if (!table) return

  try {
    await navigator.clipboard.writeText(tableToMarkdown(table))
  } catch {
    return
  }
  button.textContent = t('admin.chat.copied')
  button.classList.add('is-copied')
  setTimeout(() => {
    button.textContent = t('admin.chat.copy_table')
    button.classList.remove('is-copied')
  }, 1600)
}

// ── FlowBuilder Integration ──
const flowBuilder = ref(null)
const loadingWorkflow = ref(false)
const savingWorkflow = ref(false)
const reloadingWorkflow = ref(false)
const flowCanvas = ref(null)
const flowSvg = ref(null)

const flowZoomPercent = computed(() => {
  if (!flowBuilder.value) return '100%'
  return Math.round(flowBuilder.value.zoom * 100) + '%'
})

let draggedAgentData = null

// Group nodes size themselves around their agent rows: a label strip, then one
// card per assigned agent. Each card holds the agent name plus a "Tools" table
// nested inside it, where the tools are grouped under the skill that provides
// them and every row carries a dot for whether it is active.
const GROUP_HEADER_HEIGHT = 38
const GROUP_BOTTOM_PADDING = 14
const GROUP_MIN_HEIGHT = 78
// The closest two neighbours in the workflow may sit, measured from the bottom
// of the node that feeds to the top of the node it feeds. It is a floor rather
// than a fixed distance: a node can be left further away, but never closer, so
// no node ends up inside a group's own box and no wire has to run backwards.
const NODE_MIN_V_GAP = 28
// Where the top of the chain sits when nothing has moved it. Kept here rather
// than inline so the layout pass can lift a chain that arrives lower down.
const NODE_TOP_MARGIN = 40
const AGENT_NAME_ROW_HEIGHT = 28
const AGENT_ROW_GAP = 4
const AGENT_CARD_PAD = 4
const AGENT_CARD_BOTTOM_PAD = 4
// Name band padding, plus the room the hover-reveal remove button needs.
const AGENT_NAME_PAD_X = 12
const AGENT_NAME_ACTION_W = 26
const AGENT_NAME_FONT = '700 12px system-ui, -apple-system, "Segoe UI", sans-serif'
const TOOL_TABLE_MARGIN_TOP = 3
const TOOL_TABLE_PAD_X = 6
const TOOL_TABLE_HEADER_HEIGHT = 13
// One row for a skill heading, then one row per tool listed under it.
const SKILL_ROW_HEIGHT = 15
const TOOL_TABLE_ROW_HEIGHT = 16
// Dot and label offsets, measured from the table's left edge. A tool is indented
// one step further than the skill that provides it.
const SKILL_DOT_OFFSET = 10
const SKILL_NAME_OFFSET = 20
const TOOL_DOT_OFFSET = 22
const TOOL_NAME_OFFSET = 33
const SKILL_DOT_RADIUS = 4
const TOOL_DOT_RADIUS = 3
const TOOL_TABLE_NAME_FONT = '500 9px system-ui, -apple-system, "Segoe UI", sans-serif'
const SKILL_NAME_FONT = '600 9px system-ui, -apple-system, "Segoe UI", sans-serif'
const STATUS_ACTIVE_COLOR = '#10b981'
const STATUS_INACTIVE_COLOR = '#f43f5e'

interface ToolRow {
  id: number
  name: string
  is_active: boolean
}

// A skill heading plus the tools it provides. The trailing "Other" bucket holds
// tools the agent has that none of its skills declare, so it has no status.
interface SkillGroup {
  id: number | null
  name: string
  is_active: boolean | null
  tools: ToolRow[]
}

// Which skills and tools each agent has, plus the name and active flag behind
// every id. All of it comes from the API so the canvas never has to store it in
// the workflow.
const agentToolIds = ref<Record<number, number[]>>({})
const agentSkillIds = ref<Record<number, number[]>>({})
const toolById = ref<Record<number, { name: string; is_active: boolean }>>({})
const skillById = ref<Record<number, { name: string; is_active: boolean; tool_ids: number[] }>>({})
// Live agent rows keyed by id. A group stores the name its agent had when it
// was assigned, so reading the name from here keeps the canvas (and the label
// the backend runs the agent under) in step with the Agents panel.
const agentById = ref<Record<number, { name: string; is_active: boolean }>>({})

// True once agent rows have been fetched, which is what lets the canvas tell a
// deleted agent apart from one whose name simply has not loaded yet.
const agentsByIdLoaded = computed(() => Object.keys(agentById.value).length > 0)

// An agent that the group still points at, but which no longer exists.
function isAgentGone(agentId: number) {
  return agentsByIdLoaded.value && !agentById.value[agentId]
}

// The name to draw for a group's agent: the live one when the agent exists,
// otherwise the copy stored in the workflow so a deleted agent is still
// recognisable instead of turning into a blank row.
function agentDisplayName(agent: { id: number; name: string }) {
  const live = agentById.value[agent.id]
  return live ? live.name : agent.name
}

let textMeasureCtx: CanvasRenderingContext2D | null = null

// Measure with a canvas so trimming is exact instead of guessed per character.
function measureText(text: string, font: string) {
  if (!textMeasureCtx) textMeasureCtx = document.createElement('canvas').getContext('2d')
  if (!textMeasureCtx) return text.length * 5
  textMeasureCtx.font = font
  return textMeasureCtx.measureText(text).width
}

// A name too wide for its column is trimmed with an ellipsis.
function fitText(label: string, maxWidth: number, font: string) {
  if (measureText(label, font) <= maxWidth) return label
  let text = label
  while (text.length > 1 && measureText(text + '\u2026', font) > maxWidth) text = text.slice(0, -1)
  return text + '\u2026'
}

// Groups an agent's tools under the skills it has assigned, keeping the order
// the agent lists its skills in. Tools no assigned skill declares land in a
// trailing bucket so the list stays complete instead of dropping them.
function agentSkillGroups(agentId: number): SkillGroup[] {
  const toolIds = agentToolIds.value[agentId] || []
  if (toolIds.length === 0) return []

  const claimed = new Set<number>()
  const groups: SkillGroup[] = []

  for (const skillId of agentSkillIds.value[agentId] || []) {
    const skill = skillById.value[skillId]
    if (!skill) continue
    const tools = (skill.tool_ids || [])
      .filter(id => toolIds.includes(id) && toolById.value[id] && !claimed.has(id))
      .map((id): ToolRow => {
        claimed.add(id)
        return { id, ...toolById.value[id] }
      })
      .sort((a, b) => a.name.localeCompare(b.name))
    if (tools.length) groups.push({ id: skillId, name: skill.name, is_active: skill.is_active, tools })
  }

  const rest = toolIds
    .filter(id => toolById.value[id] && !claimed.has(id))
    .map((id): ToolRow => ({ id, ...toolById.value[id] }))
    .sort((a, b) => a.name.localeCompare(b.name))
  if (rest.length) groups.push({ id: null, name: 'Other', is_active: null, tools: rest })

  return groups
}

// Places a group's agent blocks and reports the height the box needs to wrap
// them. Each block grows by one table row per tool the agent can call.
function groupLayout(agents: { id: number; name: string }[]) {
  let offset = 0
  const blocks = (agents || []).map(agent => {
    const groups = agentSkillGroups(agent.id)
    const toolCount = groups.reduce((total, group) => total + group.tools.length, 0)
    // Agents without tools stay a plain name row; the rest grow to hold the
    // "Tools" table nested inside the card, one row per skill and per tool.
    const tableHeight = groups.length
      ? TOOL_TABLE_MARGIN_TOP + TOOL_TABLE_HEADER_HEIGHT + groups.length * SKILL_ROW_HEIGHT + toolCount * TOOL_TABLE_ROW_HEIGHT + AGENT_CARD_BOTTOM_PAD
      : 0
    const height = AGENT_NAME_ROW_HEIGHT + tableHeight
    const block = { agent, groups, offset, height }
    offset += height + AGENT_ROW_GAP
    return block
  })
  const contentHeight = blocks.length ? offset - AGENT_ROW_GAP : 0
  return {
    blocks,
    height: Math.max(GROUP_MIN_HEIGHT, GROUP_HEADER_HEIGHT + contentHeight + GROUP_BOTTOM_PADDING),
  }
}

function groupHeight(agents: { id: number; name: string }[]) {
  return groupLayout(agents).height
}

function onAgentDragStart(e, agent) {
  draggedAgentData = agent
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'copy'
    e.dataTransfer.setData('text/agent-id', String(agent.id))
    e.dataTransfer.setData('text/agent-name', agent.name)
  }
}

function onFlowDrop(e) {
  e.preventDefault()
  if (!draggedAgentData || !flowBuilder.value) return
  const svg = flowSvg.value
  if (!svg) return
  const rect = svg.getBoundingClientRect()
  const mx = (e.clientX - rect.left) / flowBuilder.value.zoom - flowBuilder.value.panX
  const my = (e.clientY - rect.top) / flowBuilder.value.zoom - flowBuilder.value.panY
  let targetNode = null
  for (const n of [...flowBuilder.value.nodes].reverse()) {
    if (mx >= n.x && mx <= n.x + n.w && my >= n.y && my <= n.y + n.h) { targetNode = n; break }
  }
  if (targetNode && targetNode.type === 'group') {
    if (!targetNode.agents) targetNode.agents = []
    if (!targetNode.agents.some(a => a.id === draggedAgentData.id)) {
      targetNode.agents.push({ id: draggedAgentData.id, name: draggedAgentData.name })
      flowBuilder.value.render()
    }
  }
  draggedAgentData = null
}

class FlowBuilder {
        constructor(el, svgEl, wire, alpine) {
            this.el = el;
            this.svg = svgEl;
            this.wire = wire;
            this.alpine = alpine;
            this.nodes = [];
            this.wires = [];
            this.nextId = 1;
            this.dragging = null;
            this.dragOffset = { x: 0, y: 0 };
            this.drawingWire = null;
            this.svgNS = 'http://www.w3.org/2000/svg';
            // Zoom / Pan
            this.zoom = 1;
            this.panX = 0;
            this.panY = 0;
            this.isPanning = false;
            this.panStart = { x: 0, y: 0 };
            this.panStartValues = { x: 0, y: 0 };
            this.minZoom = 0.3;
            this.maxZoom = 2;

            // Don't add default nodes here — loadFromWire handles it

            this.setupEvents();
        }

        addNode(type, x, y, label) {
            if (x === undefined) {
                // Place a new node one gap below the last one, on the
                // same centre line as the rest of the chain.
                const last = this.nodes[this.nodes.length - 1];
                x = type === 'group' ? 30 : 60;
                y = last ? last.y + last.h + NODE_MIN_V_GAP : 160;
            }
            if (label === undefined) {
                label = type === 'start' ? 'Start' : type === 'stop' ? 'Stop' : `Group ${this.nodes.filter(n=>n.type==='group').length + 1}`;
            }
            const h = type === 'group' ? 120 : 36;
            const w = type === 'group' ? 240 : 180;
            const node = {
                id: this.nextId++,
                type,
                label,
                x, y, w, h,
                ports: [],
            };
            // Add ports
            if (type === 'start') {
                node.ports.push({ id: `${node.id}-out`, side: 'bottom', index: 0 });
            } else if (type === 'stop') {
                node.ports.push({ id: `${node.id}-in`, side: 'top', index: 0 });
            } else if (type === 'group') {
                node.ports.push({ id: `${node.id}-in`, side: 'top', index: 0 });
                node.ports.push({ id: `${node.id}-out`, side: 'bottom', index: 0 });
            }
            this.nodes.push(node);
            this.render();
            return node;
        }

        removeNode(nodeId) {
            this.wires = this.wires.filter(w => w.fromNode !== nodeId && w.toNode !== nodeId);
            this.nodes = this.nodes.filter(n => n.id !== nodeId);
            this.render();
        }

        addWire(fromPort, toPort) {
            const fromNode = this.nodes.find(n => n.ports.some(p => p.id === fromPort));
            const toNode = this.nodes.find(n => n.ports.some(p => p.id === toPort));
            if (!fromNode || !toNode) return;
            // Prevent duplicates
            const exists = this.wires.some(w => w.fromPort === fromPort && w.toPort === toPort);
            if (exists) return;
            this.wires.push({
                id: `${fromPort}->${toPort}`,
                fromNode: fromNode.id,
                fromPort,
                toNode: toNode.id,
                toPort,
            });
            this.render();
        }

        removeWire(wireId) {
            this.wires = this.wires.filter(w => w.id !== wireId);
            this.render();
        }

        getPortPos(node, port) {
            const cx = node.x + node.w / 2;
            const cy = node.y + node.h / 2;
            if (port.side === 'top') return { x: cx, y: node.y };
            if (port.side === 'bottom') return { x: cx, y: node.y + node.h };
            return { x: cx, y: cy };
        }

        // A group is sized by the agent cards inside it, so dropping an agent in
        // makes the box taller. Nothing else moved with it, which left the node
        // below at its old y: the group grew straight over it and the wire from
        // the group's bottom ran back up into the group's own box, drawing a
        // Stop on top of the agent cards.
        //
        // NODE_MIN_V_GAP is therefore a floor and not a fixed distance: a node
        // that is already further than that from the node above it is left
        // exactly where it is, and only the ones that sit too close - or inside
        // a group that just grew - are pushed down. Working from the geometry on
        // screen also repairs a workflow that was already saved in that state,
        // and it stays quiet while a group is still short because the skill and
        // tool lists have not loaded yet - the group grows when they do and this
        // runs again.
        normalizeLayout() {
            const canvasW = this.el ? this.el.clientWidth : 0;
            this.nodes.forEach(node => {
                if (node.type === 'group') {
                    node.w = canvasW > 0 ? Math.max(180, Math.min(240, canvasW - 12)) : 240;
                    node.h = groupLayout(node.agents || []).height;
                }
            });
            this.fitHorizontally(canvasW);
            this.enforceMinGap();
        }

        // Pull the chain inside the canvas. A workflow authored against a wider
        // canvas -- the skeleton the API writes lays start, group and stop out
        // left to right -- arrives here with most of it past the right edge,
        // where the panel clips it. When any node is out of view the whole chain
        // is centred rather than each node clamped on its own, which would leave
        // the start against the left edge and the stop against the right: a
        // staircase that reads as broken. A chain that already fits is left
        // exactly where the user put it.
        fitHorizontally(canvasW) {
            if (!canvasW) return;
            const fits = (node) => node.x >= 0 && node.x + node.w <= canvasW - 2;
            if (this.nodes.every(fits)) return;
            this.nodes.forEach(node => {
                node.x = Math.max(0, Math.round((canvasW - node.w) / 2));
            });
            // Same reasoning downwards: a chain saved against a taller canvas
            // would otherwise start halfway down an empty column, so it is
            // lifted to the margin the default layout uses.
            const top = Math.min(...this.nodes.map(node => node.y));
            if (top > NODE_TOP_MARGIN) {
                this.nodes.forEach(node => { node.y += NODE_TOP_MARGIN - top; });
            }
        }

        // Nodes in the order the wires run: everything that feeds a node is
        // placed before it, so a node can read the offsets of its feeders even
        // when it has just been dragged above them. Ties, and nodes with no wire
        // at all, keep the order they already have on screen, so the layout never
        // shuffles by itself.
        chainOrder() {
            const order = [];
            const placed = new Set();
            const byY = (a, b) => a.y - b.y || a.id - b.id;
            const visit = (node) => {
                if (!node || placed.has(node.id)) return;
                placed.add(node.id);
                this.wires
                    .filter(w => w.toNode === node.id)
                    .map(w => this.nodes.find(n => n.id === w.fromNode))
                    .filter(Boolean)
                    .sort(byY)
                    .forEach(visit);
                order.push(node);
            };
            [...this.nodes].sort(byY).forEach(visit);
            return order;
        }

        // Push whatever sits too close to the node above it down until the gap
        // is exactly NODE_MIN_V_GAP, and leave everything else alone. One pass is
        // enough because chainOrder() puts every feeder before the node it
        // feeds, so a node is only looked at once the nodes above it have their
        // final bottom edge.
        enforceMinGap() {
            this.chainOrder().forEach(node => {
                let floor = null;
                this.wires
                    .filter(w => w.toNode === node.id)
                    .forEach(w => {
                        const from = this.nodes.find(n => n.id === w.fromNode);
                        if (!from) return;
                        const below = from.y + from.h + NODE_MIN_V_GAP;
                        if (floor === null || below > floor) floor = below;
                    });
                if (floor !== null && node.y < floor) node.y = floor;
            });
        }

        setupEvents() {
            let lastHoveredPort = null;

            // ── Zoom with mousewheel ──
            this.svg.addEventListener('wheel', (e) => {
                e.preventDefault();
                const rect = this.svg.getBoundingClientRect();
                const cx = (e.clientX - rect.left) / this.zoom - this.panX;
                const cy = (e.clientY - rect.top) / this.zoom - this.panY;
                const delta = e.deltaY > 0 ? 0.9 : 1.1;
                const newZoom = Math.min(this.maxZoom, Math.max(this.minZoom, this.zoom * delta));
                this.panX = (e.clientX - rect.left) / newZoom - cx;
                this.panY = (e.clientY - rect.top) / newZoom - cy;
                this.zoom = newZoom;
                this.applyTransform();
            }, { passive: false });

            // ── Pan (middle mouse button or space + left drag) ──
            const startPan = (clientX, clientY) => {
                this.isPanning = true;
                this.panStart = { x: clientX, y: clientY };
                this.panStartValues = { x: this.panX, y: this.panY };
                this.svg.style.cursor = 'grabbing';
            };

            this.svg.addEventListener('mousedown', (e) => {
                // Middle mouse button pan
                if (e.button === 1) {
                    e.preventDefault();
                    startPan(e.clientX, e.clientY);
                    return;
                }

                // Port mousedown starts null drawing (higher priority)
                const portEl = e.target.closest('[data-port-id]');
                if (portEl) {
                    e.preventDefault();
                    e.stopPropagation();
                    const fromPort = portEl.dataset.portId;
                    const node = this.nodes.find(n => n.ports.some(p => p.id === fromPort));
                    if (!node) return;
                    const port = node.ports.find(p => p.id === fromPort);
                    const pos = this.getPortPos(node, port);
                    this.drawingWire = { fromPort, fromPos: pos };
                    return;
                }

                // Node mousedown starts dragging
                const el = e.target.closest('[data-node-id]');
                if (!el) {
                    // Empty canvas area → start pan with left button too
                    startPan(e.clientX, e.clientY);
                    return;
                }
                const nodeId = parseInt(el.dataset.nodeId);
                const node = this.nodes.find(n => n.id === nodeId);
                if (!node) return;
                const rect = this.svg.getBoundingClientRect();
                const mx = (e.clientX - rect.left) / this.zoom - this.panX;
                const my = (e.clientY - rect.top) / this.zoom - this.panY;
                this.dragging = node;
                this.dragOffset = { x: mx - node.x, y: my - node.y };
                if (el) el.style.cursor = "url('data:image/svg+xml,\<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2224%22 height=%2224%22 viewBox=%220 0 24 24%22%3E\<path d=%22M9 10V4a1.5 1.5 0 0 1 3 0v4M12 6a1.5 1.5 0 0 1 3 0v4M15 6a1.5 1.5 0 0 1 3 1.5V13a6 6 0 0 1-12 0v-3a1.5 1.5 0 0 1 3 0v1%22 fill=%22%23e5e7eb%22 stroke=%22%23000%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22 /%3E\</svg%3E') 12 12, grabbing";
            });

            this.svg.addEventListener('mousemove', (e) => {
                const rect = this.svg.getBoundingClientRect();

                if (this.isPanning) {
                    this.panX = this.panStartValues.x + (e.clientX - this.panStart.x) / this.zoom;
                    this.panY = this.panStartValues.y + (e.clientY - this.panStart.y) / this.zoom;
                    this.applyTransform();
                    return;
                }

                const mx = (e.clientX - rect.left) / this.zoom - this.panX;
                const my = (e.clientY - rect.top) / this.zoom - this.panY;

                if (this.dragging) {
                    this.dragging.x = Math.max(0, mx - this.dragOffset.x);
                    this.dragging.y = Math.max(0, my - this.dragOffset.y);
                    this.renderWiresOnly();
                }

                if (this.drawingWire) {
                    // Use actual mouse position in SVG coords for accurate wire-following
                    this.renderDragWire(this.drawingWire.fromPos.x, this.drawingWire.fromPos.y, mx, my);
                }

                // Track hovered port using SVG coordinates, not screen coordinates
                const hoverEl = document.elementFromPoint(e.clientX, e.clientY);
                const portEl = hoverEl?.closest('[data-port-id]');
                lastHoveredPort = portEl ? portEl.dataset.portId : null;
            });

            const mouseup = (e) => {
                if (e.button === 1) {
                    // Middle mouse button released
                    this.isPanning = false;
                    this.svg.style.cursor = '';
                    return;
                }
                if (this.isPanning) {
                    this.isPanning = false;
                    this.svg.style.cursor = '';
                }
                if (this.dragging) {
                    // The node keeps the y it was released at. render() only
                    // pushes down whatever ended up too close to it, so a node
                    // can always be left further from its neighbour than the
                    // minimum.
                    this.dragging = null;
                    this.render();
                }
                // Reset cursor from grab to default
                const grabbed = this.svg.querySelector('[data-node-id]:active');
                if (grabbed) grabbed.style.cursor = "url('data:image/svg+xml,\<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2224%22 height=%2224%22 viewBox=%220 0 24 24%22%3E\<path d=%22M9 11V6a1.5 1.5 0 0 1 3 0v4M12 6a1.5 1.5 0 0 1 3 0v4M15 6a1.5 1.5 0 0 1 3 1.5V13a6 6 0 0 1-12 0v-3a1.5 1.5 0 0 1 3 0v1%22 fill=%22%23fff%22 stroke=%22%23000%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22 /%3E\</svg%3E') 12 12, grab";
                if (this.drawingWire) {
                    if (lastHoveredPort && lastHoveredPort !== this.drawingWire.fromPort) {
                        this.addWire(this.drawingWire.fromPort, lastHoveredPort);
                    }
                    this.drawingWire = null;
                    this.render();
                }
            };
            document.addEventListener('mouseup', mouseup);
        }

        applyTransform() {
            this.svg.style.transformOrigin = '0 0';
            this.svg.style.transform = `translate(${this.panX * this.zoom}px, ${this.panY * this.zoom}px) scale(${this.zoom})`;
        }

        // Gradients, soft shadows and the wire arrowhead live in <defs>, which
        // render() throws away with the rest of the SVG, so they are rebuilt
        // here on every pass. Referencing a missing paint server would make the
        // node it fills disappear entirely.
        ensureDefs() {
            const defs = document.createElementNS(this.svgNS, 'defs');

            const gradient = (id, stops, horizontal) => {
                const grad = document.createElementNS(this.svgNS, 'linearGradient');
                grad.setAttribute('id', id);
                grad.setAttribute('x1', '0');
                grad.setAttribute('y1', '0');
                grad.setAttribute('x2', horizontal ? '1' : '0.9');
                grad.setAttribute('y2', horizontal ? '0' : '1');
                stops.forEach(([offset, color]) => {
                    const stop = document.createElementNS(this.svgNS, 'stop');
                    stop.setAttribute('offset', offset);
                    stop.setAttribute('stop-color', color);
                    grad.appendChild(stop);
                });
                return grad;
            };

            const dropShadow = (id, dy, blur, color, opacity) => {
                const filter = document.createElementNS(this.svgNS, 'filter');
                filter.setAttribute('id', id);
                filter.setAttribute('x', '-25%');
                filter.setAttribute('y', '-40%');
                filter.setAttribute('width', '150%');
                filter.setAttribute('height', '200%');
                const shadow = document.createElementNS(this.svgNS, 'feDropShadow');
                shadow.setAttribute('dx', '0');
                shadow.setAttribute('dy', dy);
                shadow.setAttribute('stdDeviation', blur);
                shadow.setAttribute('flood-color', color);
                shadow.setAttribute('flood-opacity', opacity);
                filter.appendChild(shadow);
                return filter;
            };

            defs.appendChild(gradient('flowStartGrad', [['0', '#34d399'], ['1', '#0d9488']], false));
            defs.appendChild(gradient('flowStopGrad', [['0', '#fb7185'], ['1', '#e11d48']], false));
            defs.appendChild(gradient('flowHeaderGrad', [['0', '#e6ebfd'], ['1', '#f4ecfe']], true));
            defs.appendChild(gradient('flowAgentGrad', [['0', '#eef2ff'], ['1', '#e5eaff']], true));
            defs.appendChild(dropShadow('flowNodeShadow', '3', '4', '#4338ca', '0.16'));
            defs.appendChild(dropShadow('flowCardShadow', '2', '3', '#312e81', '0.12'));

            const marker = document.createElementNS(this.svgNS, 'marker');
            marker.setAttribute('id', 'arrowhead');
            marker.setAttribute('markerWidth', '10');
            marker.setAttribute('markerHeight', '7');
            marker.setAttribute('refX', '9');
            marker.setAttribute('refY', '3.5');
            marker.setAttribute('orient', 'auto');
            const arrow = document.createElementNS(this.svgNS, 'polygon');
            arrow.setAttribute('points', '0 0, 10 3.5, 0 7');
            arrow.setAttribute('fill', '#a5b4fc');
            marker.appendChild(arrow);
            defs.appendChild(marker);

            this.svg.appendChild(defs);
        }

        render() {
            this.svg.innerHTML = '';
            this.ensureDefs();
            // Groups resize themselves around their contents, so this runs
            // before the wires are routed: a wire has to start from the group's
            // final bottom edge, not the one it had before the agent went in.
            this.normalizeLayout();
            // Wires layer
            this.wires.forEach(w => {
                const fromNode = this.nodes.find(n => n.id === w.fromNode);
                const toNode = this.nodes.find(n => n.id === w.toNode);
                if (!fromNode || !toNode) return;
                const fromPort = fromNode.ports.find(p => p.id === w.fromPort);
                const toPort = toNode.ports.find(p => p.id === w.toPort);
                if (!fromPort || !toPort) return;
                const p1 = this.getPortPos(fromNode, fromPort);
                const p2 = this.getPortPos(toNode, toPort);
                this.drawWire(p1.x, p1.y, p2.x, p2.y, w.id);
            });
            // Nodes layer
            this.nodes.forEach(n => this.drawNode(n));
            this.applyTransform();
            this._updateCache();
        }

        renderWiresOnly() {
            // Remove only the temporary wire paths, keep the <g> groups from drawWire
            this.svg.querySelectorAll('.flow-wire-temp').forEach(el => el.remove());
            this.wires.forEach(w => {
                const fromNode = this.nodes.find(n => n.id === w.fromNode);
                const toNode = this.nodes.find(n => n.id === w.toNode);
                if (!fromNode || !toNode) return;
                const fromPort = fromNode.ports.find(p => p.id === w.fromPort);
                const toPort = toNode.ports.find(p => p.id === w.toPort);
                if (!fromPort || !toPort) return;
                const p1 = this.getPortPos(fromNode, fromPort);
                const p2 = this.getPortPos(toNode, toPort);
                // Reuse existing wire group or create one
                let g = this.svg.querySelector('g[data-wire-id="' + w.id + '"]');
                if (!g) {
                    g = document.createElementNS(this.svgNS, 'g');
                    g.dataset.wireId = w.id;
                    this.svg.appendChild(g);
                }
                // Update or create the path inside the group
                let line = g.querySelector('path.flow-wire-path');
                if (!line) {
                    line = document.createElementNS(this.svgNS, 'path');
                    line.setAttribute('class', 'flow-wire-path flow-wire');
                    g.appendChild(line);
                    // Add arrowhead marker
                    const defs = this.svg.querySelector('defs');
                    if (defs && !defs.querySelector('#arrowhead')) {
                        const marker = document.createElementNS(this.svgNS, 'marker');
                        marker.setAttribute('id', 'arrowhead');
                        marker.setAttribute('markerWidth', '8');
                        marker.setAttribute('markerHeight', '6');
                        marker.setAttribute('refX', '8');
                        marker.setAttribute('refY', '3');
                        marker.setAttribute('orient', 'auto');
                        const arrow = document.createElementNS(this.svgNS, 'polygon');
                        arrow.setAttribute('points', '0 0, 8 3, 0 6');
                        arrow.setAttribute('fill', '#6b7280');
                        marker.appendChild(arrow);
                        defs.appendChild(marker)
                    }
                }
                line.setAttribute('d', this.bezierPath(p1.x, p1.y, p2.x, p2.y));
            });
        }

        renderDragWire(x1, y1, x2, y2) {
            let line = this.svg.querySelector('.flow-wire-drag');
            if (!line) {
                line = document.createElementNS(this.svgNS, 'path');
                line.setAttribute('class', 'flow-wire-drag');
                this.svg.appendChild(line);
            }
            line.setAttribute('d', this.bezierPath(x1, y1, x2, y2));
        }

        drawWire(x1, y1, x2, y2, id) {
            const g = document.createElementNS(this.svgNS, 'g');
            g.dataset.wireId = id;

            const line = document.createElementNS(this.svgNS, 'path');
            line.setAttribute('d', this.bezierPath(x1, y1, x2, y2));
            line.setAttribute('class', 'flow-wire');
            g.appendChild(line);

            // Direction arrow at midpoint — shows flow direction
            const mx = (x1 + x2) / 2;
            const my = (y1 + y2) / 2;
            const angle = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;

            const arrowG = document.createElementNS(this.svgNS, 'g');
            arrowG.style.pointerEvents = 'none';
            arrowG.setAttribute('transform', 'translate(' + mx + ', ' + my + ') rotate(' + angle + ')');

            const arrow = document.createElementNS(this.svgNS, 'path');
            arrow.setAttribute('d', 'M -7 -5 L 5 0 L -7 5 Z');
            arrow.setAttribute('fill', '#6366f1');
            arrow.setAttribute('stroke', 'none');
            arrowG.appendChild(arrow);

            g.appendChild(arrowG);

            // Double-click null to delete
            const hitArea = document.createElementNS(this.svgNS, 'path');
            hitArea.setAttribute('d', this.bezierPath(x1, y1, x2, y2));
            hitArea.setAttribute('fill', 'none');
            hitArea.setAttribute('stroke', 'transparent');
            hitArea.setAttribute('stroke-width', '14');
            hitArea.style.cursor = 'pointer';
            hitArea.addEventListener('dblclick', function(e) {
                e.stopPropagation();
                this.removeWire(id);
            }.bind(this));
            g.appendChild(hitArea);

            this.svg.appendChild(g);
        }

        bezierPath(x1, y1, x2, y2) {
            const dy = Math.abs(y2 - y1) * 0.5;
            return `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`;
        }

        drawNode(node) {
            const g = document.createElementNS(this.svgNS, 'g');
            g.dataset.nodeId = node.id;
            g.style.cursor = "url('data:image/svg+xml,\<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2224%22 height=%2224%22 viewBox=%220 0 24 24%22%3E\<path d=%22M9 11V6a1.5 1.5 0 0 1 3 0v4M12 6a1.5 1.5 0 0 1 3 0v4M15 6a1.5 1.5 0 0 1 3 1.5V13a6 6 0 0 1-12 0v-3a1.5 1.5 0 0 1 3 0v1%22 fill=%22%23fff%22 stroke=%22%23000%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22 /%3E\</svg%3E') 12 12, grab";

            if (node.type === 'start' || node.type === 'stop') {
                const rect = document.createElementNS(this.svgNS, 'rect');
                rect.setAttribute('x', node.x);
                rect.setAttribute('y', node.y);
                rect.setAttribute('width', node.w);
                rect.setAttribute('height', node.h);
                rect.setAttribute('rx', '18');
                rect.setAttribute('ry', '18');
                rect.setAttribute('class', `flow-node flow-node-${node.type}`);
                // Set here rather than in CSS: a CSS fill would win over this
                // presentation attribute and the gradient would never show.
                rect.setAttribute('fill', node.type === 'start' ? 'url(#flowStartGrad)' : 'url(#flowStopGrad)');
                rect.setAttribute('filter', 'url(#flowNodeShadow)');
                g.appendChild(rect);

                const text = document.createElementNS(this.svgNS, 'text');
                text.setAttribute('x', node.x + node.w / 2);
                text.setAttribute('y', node.y + node.h / 2);
                text.setAttribute('class', 'flow-node-text flow-node-text-title');
                text.textContent = node.label;
                g.appendChild(text);
            } else {
                // Group node. Width, height and position were all settled by
                // normalizeLayout() before render() routed the wires, and the
                // card has to be drawn exactly where those wires end: moving it
                // here, which is after the wires are drawn, used to leave every
                // wire pointing at the card's old position.
                const layout = groupLayout(node.agents || []);
                const rect = document.createElementNS(this.svgNS, 'rect');
                rect.setAttribute('x', node.x);
                rect.setAttribute('y', node.y);
                rect.setAttribute('width', node.w);
                rect.setAttribute('height', node.h);
                rect.setAttribute('class', 'flow-node flow-node-group');
                rect.setAttribute('filter', 'url(#flowCardShadow)');
                // Accept drops from agent list
                rect.addEventListener('dragover', (e) => { e.preventDefault(); });
                rect.addEventListener('drop', (e) => {
                    e.preventDefault();
                    const agentId = e.dataTransfer.getData('text/agent-id');
                    const agentName = e.dataTransfer.getData('text/agent-name');
                    if (!agentId) return;
                    // Store agent assignments on the node
                    if (!node.agents) node.agents = [];
                    if (!node.agents.some(a => a.id === parseInt(agentId))) {
                        node.agents.push({ id: parseInt(agentId), name: agentName });
                    }
                    this.render();
                });
                g.appendChild(rect);

                // Tinted header band: a rounded rect with its bottom corners
                // squared off, inset by the stroke width so the border stays
                // visible around it.
                const headerH = GROUP_HEADER_HEIGHT - 4;
                const header = document.createElementNS(this.svgNS, 'rect');
                header.setAttribute('x', node.x + 1);
                header.setAttribute('y', node.y + 1);
                header.setAttribute('width', node.w - 2);
                header.setAttribute('height', headerH);
                header.setAttribute('rx', '12');
                header.setAttribute('fill', 'url(#flowHeaderGrad)');
                g.appendChild(header);

                // Square off the band's bottom edge by overdrawing its lower half.
                const headerBase = document.createElementNS(this.svgNS, 'rect');
                headerBase.setAttribute('x', node.x + 1);
                headerBase.setAttribute('y', node.y + 1 + headerH / 2);
                headerBase.setAttribute('width', node.w - 2);
                headerBase.setAttribute('height', headerH / 2);
                headerBase.setAttribute('fill', 'url(#flowHeaderGrad)');
                g.appendChild(headerBase);

                // Editable group name: uses foreignObject with an HTML input
                // centred in the header band rather than sitting low in it.
                const headerTextH = 24;
                const foName = document.createElementNS(this.svgNS, 'foreignObject');
                foName.setAttribute('x', node.x + 12);
                foName.setAttribute('y', node.y + 1 + (headerH - headerTextH) / 2);
                foName.setAttribute('width', node.w - 32);
                foName.setAttribute('height', String(headerTextH));
                const nameInput = document.createElement('input');
                nameInput.type = 'text';
                nameInput.value = node.label || '';
                nameInput.style.cssText = 'width:100%;height:100%;border:none;background:transparent;font-size:13px;font-weight:700;color:#3730a3;letter-spacing:0.01em;text-align:center;outline:none;';
                nameInput.addEventListener('mousedown', (e) => e.stopPropagation());
                nameInput.addEventListener('click', (e) => e.stopPropagation());
                nameInput.addEventListener('dblclick', (e) => e.stopPropagation());
                nameInput.addEventListener('input', (e) => {
                    node.label = e.target.value;
                });
                nameInput.addEventListener('blur', () => {
                    if (!node.label || !node.label.trim()) {
                        node.label = 'Unnamed Group';
                        nameInput.value = node.label;
                    }
                });
                // Prevent drag initiation on input
                nameInput.addEventListener('pointerdown', (e) => e.stopPropagation());
                foName.appendChild(nameInput);
                g.appendChild(foName);

                // Delete button (hover to reveal)
                const delG = document.createElementNS(this.svgNS, 'g');
                delG.style.display = 'none';
                delG.style.cursor = 'pointer';

                // Centred on the header band and on the same column as the
                // agent rows' buttons. Pinned to node.y + 12 and
                // node.x + node.w - 10 it hung over the card's rounded
                // top-right corner, half outside the border and above the
                // group name, which read as a misplaced control.
                const delCx = node.x + node.w - 16;
                const delCy = node.y + 1 + headerH / 2;

                const delBg = document.createElementNS(this.svgNS, 'circle');
                delBg.setAttribute('cx', delCx);
                delBg.setAttribute('cy', delCy);
                delBg.setAttribute('r', '9');
                delBg.setAttribute('fill', '#fff1f2');
                delBg.setAttribute('stroke', '#fda4af');
                delBg.setAttribute('stroke-width', '1');
                delG.appendChild(delBg);

                const delX = document.createElementNS(this.svgNS, 'text');
                delX.setAttribute('x', delCx);
                delX.setAttribute('y', delCy);
                delX.setAttribute('text-anchor', 'middle');
                delX.setAttribute('dominant-baseline', 'central');
                delX.setAttribute('font-size', '14');
                delX.setAttribute('fill', '#e11d48');
                delX.textContent = '\u00d7';
                delG.appendChild(delX);

                delG.addEventListener('mousedown', (e) => e.stopPropagation());
                delG.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.removeNode(node.id);
                });
                g.appendChild(delG);

                // Show delete button on hover
                rect.addEventListener('mouseenter', () => { delG.style.display = ''; });
                rect.addEventListener('mouseleave', () => {
                    setTimeout(() => {
                        const hovered = document.querySelector('[data-node-id="' + node.id + '"]:hover');
                        if (!hovered) delG.style.display = 'none';
                    }, 50);
                });

                // Render assigned agents inside group
                    if (node.agents && node.agents.length > 0) {
                    const ns = this.svgNS;
                    layout.blocks.forEach((block) => {
                        const agent = block.agent;
                        const yStart = node.y + GROUP_HEADER_HEIGHT + block.offset;

                        // === Agent title ===
                        const _r = () => this.render();

                            // Agent card: wraps the name row and the tools table
                            // Inset from the group's border by the same 4px on
                            // both sides; the old width left 3px on the right,
                            // which showed up as a card that sat off-centre.
                            var agentH = block.height;
                            var agentX = node.x + 4;
                            var agentBorder = document.createElementNS(ns, 'rect');
                            agentBorder.setAttribute('x', agentX);
                            agentBorder.setAttribute('y',  yStart);
                            var agentBW = node.w - 8;
                            agentBorder.setAttribute('width',  agentBW);
                            agentBorder.setAttribute('height',  agentH);
                            agentBorder.setAttribute('rx', '10');
                            agentBorder.setAttribute('fill', '#ffffff');
                            agentBorder.setAttribute('stroke', '#e0e6f7');
                            agentBorder.setAttribute('stroke-width', '1');
                            agentBorder.setAttribute('filter', 'url(#flowCardShadow)');
                            g.appendChild(agentBorder);

                            // Name band. Squared off along the bottom the same way
                            // the group header is, so the agent reads as a titled
                            // card rather than a pill floating on a white box.
                            // The band, its label and the remove button share one
                            // group so a pointer move between them is not a leave:
                            // otherwise the x hid itself mid-click and the click
                            // fell through to the canvas and panned instead.
                            var bandWrap = document.createElementNS(ns, 'g');
                            g.appendChild(bandWrap);
                            var rmHideTimer = null;
                            var bgH = AGENT_NAME_ROW_HEIGHT - 2;
                            var bg = document.createElementNS(ns, 'rect');
                            bg.setAttribute('x', agentX + 1);
                            bg.setAttribute('y', yStart + 1);
                            bg.setAttribute('width', agentBW - 2);
                            bg.setAttribute('height', bgH);
                            bg.setAttribute('rx', '9');
                            bg.setAttribute('fill', 'url(#flowAgentGrad)');
                            bandWrap.appendChild(bg);

                            var bgBase = document.createElementNS(ns, 'rect');
                            bgBase.setAttribute('x', agentX + 1);
                            bgBase.setAttribute('y', yStart + 1 + bgH / 2);
                            bgBase.setAttribute('width', agentBW - 2);
                            bgBase.setAttribute('height', bgH / 2);
                            bgBase.setAttribute('fill', 'url(#flowAgentGrad)');
                            bandWrap.appendChild(bgBase);

                            var bgRule = document.createElementNS(ns, 'line');
                            bgRule.setAttribute('x1', agentX + 1);
                            bgRule.setAttribute('x2', agentX + agentBW - 1);
                            bgRule.setAttribute('y1', yStart + AGENT_NAME_ROW_HEIGHT - 1);
                            bgRule.setAttribute('y2', yStart + AGENT_NAME_ROW_HEIGHT - 1);
                            bgRule.setAttribute('stroke', '#dbe2fb');
                            bgRule.setAttribute('stroke-width', '1');
                            bandWrap.appendChild(bgRule);

                            // Centred with dominant-baseline so descenders stay
                            // inside the band, and trimmed so a long name never
                            // runs under the remove button.
                            var nameMax = agentBW - AGENT_NAME_PAD_X - AGENT_NAME_ACTION_W;
                            // The workflow keeps a copy of the name the agent
                            // had when it was assigned, which goes stale as soon
                            // as the agent is renamed. Draw the live name and
                            // fall back to the stored one only for an agent that
                            // has been deleted since.
                            var agentLabel = agentDisplayName(agent);
                            var agentGone = isAgentGone(agent.id);
                            if (agentGone) agentLabel += ' (removed)';
                            var nameText = document.createElementNS(ns, 'text');
                            nameText.setAttribute('x', agentX + AGENT_NAME_PAD_X);
                            nameText.setAttribute('y', yStart + AGENT_NAME_ROW_HEIGHT / 2 - 1);
                            nameText.setAttribute('dominant-baseline', 'central');
                            nameText.setAttribute('font-size', '12');
                            nameText.setAttribute('letter-spacing', '0.01em');
                            nameText.setAttribute('fill', agentGone ? '#be123c' : '#3730a3');
                            nameText.setAttribute('font-weight', '700');
                            nameText.setAttribute('text-anchor', 'start');
                            nameText.textContent = fitText(agentLabel, nameMax, AGENT_NAME_FONT);
                            var nameTip = document.createElementNS(ns, 'title');
                            nameTip.textContent = agentGone
                                ? agentLabel + ' \u2014 this agent no longer exists, so the group runs nothing for it'
                                : agentLabel;
                            nameText.appendChild(nameTip);
                            bandWrap.appendChild(nameText);

                            // Remove X (hover-reveal, far right)
                            var rmG = document.createElementNS(ns, 'g');
                            rmG.style.display = 'none';
                            rmG.style.cursor = 'pointer';
                            var rmBg = document.createElementNS(ns, 'circle');
                            rmBg.setAttribute('cx',  (agentX + agentBW - 13));
                            rmBg.setAttribute('cy',  (yStart + AGENT_NAME_ROW_HEIGHT / 2 - 1));
                            rmBg.setAttribute('r', '8');
                            rmBg.setAttribute('fill', '#fff1f2');
                            rmBg.setAttribute('stroke', '#fda4af');
                            rmBg.setAttribute('stroke-width', '1');
                            rmG.appendChild(rmBg);
                            var rmX = document.createElementNS(ns, 'text');
                            rmX.setAttribute('x',  (agentX + agentBW - 13));
                            rmX.setAttribute('y',  (yStart + AGENT_NAME_ROW_HEIGHT / 2 - 1));
                            rmX.setAttribute('text-anchor', 'middle');
                            rmX.setAttribute('dominant-baseline', 'central');
                            rmX.setAttribute('font-size', '10');
                            rmX.setAttribute('fill', '#e11d48');
                            rmX.textContent = '\u00d7';
                            rmG.appendChild(rmX);
                            rmG.addEventListener('mousedown', function(e){e.stopPropagation()});
                            rmG.addEventListener('click', function(e) {
                                e.stopPropagation();
                                node.agents = node.agents.filter(function(a){return a.id !== agent.id});
                                _r();
                            });
                            bandWrap.appendChild(rmG);
                            bandWrap.addEventListener('mouseenter', function(){
                                if (rmHideTimer) { clearTimeout(rmHideTimer); rmHideTimer = null; }
                                rmG.style.display = '';
                            });
                            bandWrap.addEventListener('mouseleave', function(){
                                if (rmHideTimer) clearTimeout(rmHideTimer);
                                rmHideTimer = setTimeout(function(){
                                    rmHideTimer = null;
                                    rmG.style.display = 'none';
                                }, 50);
                            });

                            // The agent's skills and the tools each one provides,
                            // listed inside its own card so the agent and its
                            // capabilities read as one unit.
                            if (block.groups.length > 0) {
                                var tableX = agentX + AGENT_CARD_PAD;
                                var tableW = agentBW - AGENT_CARD_PAD * 2;
                                var tableY = yStart + AGENT_NAME_ROW_HEIGHT + TOOL_TABLE_MARGIN_TOP;
                                var toolCount = block.groups.reduce(function(n, grp){return n + grp.tools.length}, 0);
                                var tableH = TOOL_TABLE_HEADER_HEIGHT + block.groups.length * SKILL_ROW_HEIGHT + toolCount * TOOL_TABLE_ROW_HEIGHT;
                                var skillDotX = tableX + SKILL_DOT_OFFSET;
                                var skillColX = tableX + SKILL_NAME_OFFSET;
                                var toolDotX = tableX + TOOL_DOT_OFFSET;
                                var toolColX = tableX + TOOL_NAME_OFFSET;

                                var toolTableBg = document.createElementNS(ns, 'rect');
                                toolTableBg.setAttribute('x', tableX);
                                toolTableBg.setAttribute('y', tableY);
                                toolTableBg.setAttribute('width', tableW);
                                toolTableBg.setAttribute('height', tableH);
                                toolTableBg.setAttribute('rx', '8');
                                toolTableBg.setAttribute('fill', '#fbfcff');
                                toolTableBg.setAttribute('stroke', '#e6eaf7');
                                toolTableBg.setAttribute('stroke-width', '1');
                                g.appendChild(toolTableBg);

                                var headTools = document.createElementNS(ns, 'text');
                                headTools.setAttribute('x', tableX + TOOL_TABLE_PAD_X);
                                headTools.setAttribute('y', tableY + TOOL_TABLE_HEADER_HEIGHT / 2);
                                headTools.setAttribute('dominant-baseline', 'central');
                                headTools.setAttribute('font-size', '8');
                                headTools.setAttribute('font-weight', '700');
                                headTools.setAttribute('letter-spacing', '0.7');
                                headTools.setAttribute('fill', '#8a93b2');
                                headTools.textContent = 'Tools';
                                g.appendChild(headTools);

                                var skillNameMax = tableW - SKILL_NAME_OFFSET - TOOL_TABLE_PAD_X;
                                var toolNameMax = tableW - TOOL_NAME_OFFSET - TOOL_TABLE_PAD_X;
                                var rowY = tableY + TOOL_TABLE_HEADER_HEIGHT;

                                block.groups.forEach(function(skillGroup) {
                                    // Separator above every skill heading
                                    var skillRowLine = document.createElementNS(ns, 'line');
                                    skillRowLine.setAttribute('x1', tableX);
                                    skillRowLine.setAttribute('x2', tableX + tableW);
                                    skillRowLine.setAttribute('y1', rowY);
                                    skillRowLine.setAttribute('y2', rowY);
                                    skillRowLine.setAttribute('stroke', '#edf0f9');
                                    skillRowLine.setAttribute('stroke-width', '1');
                                    g.appendChild(skillRowLine);

                                    var skillRowMid = rowY + SKILL_ROW_HEIGHT / 2;

                                    // Green when the skill is active, red when it is not.
                                    var skillDot = document.createElementNS(ns, 'circle');
                                    skillDot.setAttribute('cx', skillDotX);
                                    skillDot.setAttribute('cy', skillRowMid);
                                    skillDot.setAttribute('r', String(SKILL_DOT_RADIUS));
                                    if (skillGroup.is_active === null) {
                                        // Trailing bucket holding tools no skill
                                        // declares, so there is no status to show.
                                        skillDot.setAttribute('fill', '#f8fafc');
                                        skillDot.setAttribute('stroke', '#dfe4f5');
                                        skillDot.setAttribute('stroke-width', '1');
                                    } else {
                                        skillDot.setAttribute('fill', skillGroup.is_active ? STATUS_ACTIVE_COLOR : STATUS_INACTIVE_COLOR);
                                        var skillDotTip = document.createElementNS(ns, 'title');
                                        skillDotTip.textContent = skillGroup.is_active ? 'Active' : 'Inactive';
                                        skillDot.appendChild(skillDotTip);
                                    }
                                    g.appendChild(skillDot);

                                    var skillNameText = document.createElementNS(ns, 'text');
                                    skillNameText.setAttribute('x', skillColX);
                                    skillNameText.setAttribute('y', skillRowMid);
                                    skillNameText.setAttribute('dominant-baseline', 'central');
                                    skillNameText.setAttribute('font-size', '9');
                                    skillNameText.setAttribute('font-weight', '600');
                                    skillNameText.setAttribute('fill', skillGroup.is_active === false ? '#a3abc4' : '#1e2438');
                                    skillNameText.textContent = fitText(skillGroup.name, skillNameMax, SKILL_NAME_FONT);
                                    // Full name on hover when the row had to be trimmed
                                    var skillNameTip = document.createElementNS(ns, 'title');
                                    skillNameTip.textContent = skillGroup.name;
                                    skillNameText.appendChild(skillNameTip);
                                    g.appendChild(skillNameText);

                                    rowY += SKILL_ROW_HEIGHT;

                                    skillGroup.tools.forEach(function(tool) {
                                        var toolRowMid = rowY + TOOL_TABLE_ROW_HEIGHT / 2;

                                        var toolDot = document.createElementNS(ns, 'circle');
                                        toolDot.setAttribute('cx', toolDotX);
                                        toolDot.setAttribute('cy', toolRowMid);
                                        toolDot.setAttribute('r', String(TOOL_DOT_RADIUS));
                                        toolDot.setAttribute('fill', tool.is_active ? STATUS_ACTIVE_COLOR : STATUS_INACTIVE_COLOR);
                                        var toolDotTip = document.createElementNS(ns, 'title');
                                        toolDotTip.textContent = tool.is_active ? 'Active' : 'Inactive';
                                        toolDot.appendChild(toolDotTip);
                                        g.appendChild(toolDot);

                                        var toolNameText = document.createElementNS(ns, 'text');
                                        toolNameText.setAttribute('x', toolColX);
                                        toolNameText.setAttribute('y', toolRowMid);
                                        toolNameText.setAttribute('dominant-baseline', 'central');
                                        toolNameText.setAttribute('font-size', '9');
                                        toolNameText.setAttribute('font-weight', '500');
                                        toolNameText.setAttribute('fill', tool.is_active ? '#4a5268' : '#a3abc4');
                                        toolNameText.textContent = fitText(tool.name, toolNameMax, TOOL_TABLE_NAME_FONT);
                                        // Full name on hover when the row had to be trimmed
                                        var toolNameTip = document.createElementNS(ns, 'title');
                                        toolNameTip.textContent = tool.name;
                                        toolNameText.appendChild(toolNameTip);
                                        g.appendChild(toolNameText);

                                        rowY += TOOL_TABLE_ROW_HEIGHT;
                                    });
                                });
                            }

                                           });
                }
            }

            // Ports
            node.ports.forEach(port => {
                const pos = this.getPortPos(node, port);
                const circle = document.createElementNS(this.svgNS, 'circle');
                circle.setAttribute('cx', pos.x);
                circle.setAttribute('cy', pos.y);
                circle.setAttribute('r', '5');
                circle.setAttribute('class', 'flow-port');
                circle.dataset.portId = port.id;
                g.appendChild(circle);
            });

            this.svg.appendChild(g);
        }

        toJSON() {
            return {
                nodes: this.nodes.map(n => ({
                    id: n.id,
                    type: n.type,
                    label: n.label,
                    x: Math.round(n.x),
                    y: Math.round(n.y),
                    w: n.w,
                    h: n.h,
                    agents: n.agents ? n.agents.map(a => ({ id: a.id, name: a.name })) : [],
                })),
                wires: this.wires.map(w => ({
                    id: w.id,
                    fromNode: w.fromNode,
                    fromPort: w.fromPort,
                    toNode: w.toNode,
                    toPort: w.toPort,
                })),
            };
        }

        resetToDefault() {
            this.nodes = [];
            this.wires = [];
            this.nextId = 1;
            const groupY = NODE_TOP_MARGIN + 36 + NODE_MIN_V_GAP;
            this.addNode('start', 60, NODE_TOP_MARGIN);
            this.addNode('group', 30, groupY, 'Default Group');
            // An empty group is exactly GROUP_MIN_HEIGHT tall, so the stop goes
            // one gap under that rather than under the height addNode() assumes
            // for a brand new group.
            this.addNode('stop', 60, groupY + groupHeight([]) + NODE_MIN_V_GAP);
            this.addWire('1-out', '2-in');
            this.addWire('2-out', '3-in');
        }

        fromJSON(data) {
            if (!data || !data.nodes) return;
            this.nodes = data.nodes.map(n => {
                const h = n.type === 'group' ? 120 : 36;
                const w = n.type === 'group' ? 240 : 100;
                const ports = [];
                if (n.type === 'start') ports.push({ id: `${n.id}-out`, side: 'bottom', index: 0 });
                else if (n.type === 'stop') ports.push({ id: `${n.id}-in`, side: 'top', index: 0 });
                else {
                    ports.push({ id: `${n.id}-in`, side: 'top', index: 0 });
                    ports.push({ id: `${n.id}-out`, side: 'bottom', index: 0 });
                }
                // A group is sized by its agent rows, so a stored height would
                // go stale the moment the rows change. Derive it instead.
                const gh = n.type === 'group' ? groupHeight(n.agents || []) : h;
                return { ...n, w: n.w || w, h: gh, ports, agents: (n.agents || []).map(a => ({ id: a.id, name: a.name })) };
            });
            this.wires = (data.wires || []).slice();
            this.nextId = Math.max(...this.nodes.map(n => n.id), 0) + 1;
            this.render();
        }

        _updateCache() {
            if (!window._flowCache) window._flowCache = {};
            const projectId = selectedProjectId.value;
            if (projectId) {
                window._flowCache[projectId] = this.toJSON();
            }
        }

        reloadFromWire() {
            this.nodes = [];
            this.wires = [];
            this.nextId = 1;
            reloadingWorkflow.value = true;
            this.loadFromWire();
        }

        loadFromWire() {
            const projectId = selectedProjectId.value;
            if (!projectId) {
                reloadingWorkflow.value = false;
                return Promise.resolve();
            }
            return api.get('/admin/projects/' + projectId + '/workflow').then(r => { const d = r.data || r; return typeof d.workflow === 'string' ? d.workflow : JSON.stringify(d.workflow || d); }).then(jsonStr => {
                if (jsonStr && jsonStr.length > 2) {
                    try {
                        const parsed = JSON.parse(jsonStr);
                        if (parsed && parsed.nodes && parsed.nodes.length) {
                            this.fromJSON(parsed);
                            reloadingWorkflow.value = false;
                            return;
                        }
                    } catch(e) { console.warn('Invalid workflow data', e); }
                }
                // Empty or invalid — reset to default
                this.resetToDefault();
                reloadingWorkflow.value = false;
            }).catch(() => {
                reloadingWorkflow.value = false;
            });
        }

        save() {
            const data = this.toJSON();
            api.put('/admin/projects/' + selectedProjectId.value, { workflow: data }).then(() => {this.loadFromWire()}).catch(e => { console.warn('save failed', e); }).then(() => {
                // Re-render after Livewire DOM morph (prevents SVG clearing on re-render)
                this.render();
                savingWorkflow.value = false;
            }).catch(() => {
                savingWorkflow.value = false;
            });
        }
    }
function initFlowBuilder() {
  if (!flowCanvas.value || !flowSvg.value) { setTimeout(initFlowBuilder, 50); return }
  const fb = new FlowBuilder(flowCanvas.value, flowSvg.value)
  flowBuilder.value = fb
  const pid = selectedProjectId.value
  const cache = window._flowCache && window._flowCache[pid]
  if (cache && cache.nodes && cache.nodes.length) { fb.fromJSON(cache) }
  const canvasEl = flowCanvas.value
  if (!canvasEl) return
  const ro = new ResizeObserver(() => {
    const el = flowCanvas.value
    if (!el) return
    const rect = el.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return
    const svg = flowSvg.value
    if (svg) svg.setAttribute('viewBox', `0 0 ${rect.width} ${rect.height}`)
    if (flowBuilder.value) flowBuilder.value.render()
  })
  ro.observe(canvasEl)
  let guard = false
  const mo = new MutationObserver(() => {
    if (!guard && flowBuilder.value && flowSvg.value.children.length === 0 && flowBuilder.value.nodes.length > 0) {
      guard = true; flowBuilder.value.render(); setTimeout(() => { guard = false }, 100)
    }
  })
  mo.observe(flowSvg.value, { childList: true })
  if (selectedProjectId.value) {
    reloadingWorkflow.value = true
    const checkAndLoad = () => {
      if (flowCanvas.value && flowCanvas.value.offsetWidth > 0) {
        fb.loadFromWire()
      } else {
        setTimeout(checkAndLoad, 100)
      }
    }
    setTimeout(checkAndLoad, 100)
  }
}

function addFlowGroup() {
  if (!flowBuilder.value) { setTimeout(addFlowGroup, 50); return }
  flowBuilder.value.addNode('group')
}

function reloadFlow() {
  if (!flowBuilder.value) { setTimeout(reloadFlow, 50); return }
  reloadingWorkflow.value = true
  flowBuilder.value.reloadFromWire()
}

async function saveFlow() {
  if (!flowBuilder.value) { setTimeout(saveFlow, 50); return }
  savingWorkflow.value = true
  try {
    // Persists the current canvas (nodes, wires and agent assignments) to the
    // project so the backend agent loop picks up the latest wiring.
    flowBuilder.value.save()
  } catch(e) {
    console.warn('save failed', e)
    savingWorkflow.value = false
  }
}

function flowZoomIn() {
  if (!flowBuilder.value) return
  const newZoom = Math.min(flowBuilder.value.maxZoom, flowBuilder.value.zoom * 1.25)
  const cw = flowCanvas.value?.offsetWidth || 0, ch = flowCanvas.value?.offsetHeight || 0
  flowBuilder.value.panX = (cw / 2) / newZoom
  flowBuilder.value.panY = (ch / 2) / newZoom
  flowBuilder.value.zoom = newZoom
  flowBuilder.value.applyTransform()
}

function flowZoomOut() {
  if (!flowBuilder.value) return
  const newZoom = Math.max(flowBuilder.value.minZoom, flowBuilder.value.zoom / 1.25)
  const cw = flowCanvas.value?.offsetWidth || 0, ch = flowCanvas.value?.offsetHeight || 0
  flowBuilder.value.panX = (cw / 2) / newZoom
  flowBuilder.value.panY = (ch / 2) / newZoom
  flowBuilder.value.zoom = newZoom
  flowBuilder.value.applyTransform()
}

function flowZoomReset() {
  if (!flowBuilder.value) return
  flowBuilder.value.zoom = 1
  flowBuilder.value.panX = 0
  flowBuilder.value.panY = 0
  flowBuilder.value.applyTransform()
}
// ── Initialization ──

onMounted(() => {
  loadProjects()
  loadActiveSkills()
  loadAgentTools()
  // startPolling()
  nextTick(() => initFlowBuilder())
})

function connectChatSocket() {
  if (chatSocket && chatSocket.readyState === WebSocket.OPEN) return
  const token = localStorage.getItem('token')
  if (!token || !selectedChatId.value) return
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${protocol}://${WS_BASE_URL}/ws/chats/${selectedChatId.value}?token=${encodeURIComponent(token)}`
  chatSocket = new WebSocket(url)
  chatSocket.onopen = () => { console.debug('WS connected') }
  chatSocket.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data.type === 'new_message') {
        const msg = data.message
        const exists = messages.value.some(m => m.id === msg.id)
        if (!exists) {
          messages.value.push(msg)
          nextTick(scrollToBottom)
        }
      } else if (data.type === 'typing') {
                const user = data.user_name || 'Agent'
        typingUser.value = user
        nextTick(scrollToBottom)
        if (typingTimer) clearTimeout(typingTimer)
        typingTimer = setTimeout(() => { typingUser.value = null }, 3000)
      } else if (data.type === 'stop_typing') {
        if (!data.user_name || typingUser.value === data.user_name) {
          typingUser.value = null
        }
      } else if (data.type === 'agent_loop_status') {
        agentLoopRunning.value = data.status === 'running' || data.status === 'stopping' || data.status === 'busy'
        agentLoopStopping.value = data.status === 'stopping'
        if (data.status === 'idle') {
          typingUser.value = null
        }
      }
    } catch {}
  }
  chatSocket.onclose = () => {
    console.debug('WS disconnected')
    // Auto-reconnect after 3s if chat is still selected
    if (selectedChatId.value) {
      setTimeout(connectChatSocket, 3000)
    }
  }
  chatSocket.onerror = () => {}
}

function disconnectChatSocket() {
  if (chatSocket) {
    chatSocket.close()
    chatSocket = null
  }
  agentLoopRunning.value = false
  agentLoopStopping.value = false
  typingUser.value = null
}

onUnmounted(() => {
  disconnectChatSocket()
})

// ── API ──

async function loadProjects() {
  loadingProjects.value = true
  try {
    projects.value = await fetchProjects()
    if (!selectedProjectId.value && projects.value.length > 0) {
      selectFirstProject()
    }
  } catch (e) {
    console.error('Failed to load projects', e)
  } finally {
    loadingProjects.value = false
  }
}

async function loadActiveSkills() {
  try {
    const res = await api.get('/admin/skills')
    activeSkills.value = (res.data || []).filter((skill: Skill) => skill.is_active)
  } catch (e) {
    console.error('Failed to load active skills', e)
  }
}

// The workflow canvas lists each agent's tools under the skills that provide
// them, so it needs the agent -> skill/tool mapping plus the name and active
// flag of every skill and tool behind those ids.
async function loadAgentTools() {
  // This runs alongside the rest of the page's startup traffic and can lose its
  // first race, which would leave every agent without a tool list until reload.
  for (let attempt = 0; ; attempt++) {
    try {
      const [agentsRes, toolsRes, skillsRes] = await Promise.all([
        api.get('/admin/agents'),
        api.get('/admin/tools'),
        api.get('/admin/skills'),
      ])
      const toolIdsByAgent: Record<number, number[]> = {}
      const skillIdsByAgent: Record<number, number[]> = {}
      const agentsById: Record<number, { name: string; is_active: boolean }> = {}
      for (const agent of agentsRes.data || []) {
        toolIdsByAgent[agent.id] = agent.tool_ids || []
        skillIdsByAgent[agent.id] = agent.skill_ids || []
        agentsById[agent.id] = { name: agent.name, is_active: agent.is_active }
      }
      agentToolIds.value = toolIdsByAgent
      agentSkillIds.value = skillIdsByAgent
      agentById.value = agentsById

      const byId: Record<number, { name: string; is_active: boolean }> = {}
      for (const tool of toolsRes.data || []) byId[tool.id] = { name: tool.name, is_active: tool.is_active }
      toolById.value = byId

      // Inactive skills are loaded too so the canvas can show them in red.
      const skillsById: Record<number, { name: string; is_active: boolean; tool_ids: number[] }> = {}
      for (const skill of skillsRes.data || []) {
        skillsById[skill.id] = { name: skill.name, is_active: skill.is_active, tool_ids: skill.tool_ids || [] }
      }
      skillById.value = skillsById

      // Group boxes grow to fit their tool tables, so redraw once the data lands.
      flowBuilder.value?.render()
      return
    } catch (e) {
      if (attempt >= 1) {
        console.error('Failed to load agent tools', e)
        return
      }
      await new Promise(resolve => setTimeout(resolve, 500))
    }
  }
}

function activeSkillIds() {
  return new Set(activeSkills.value.map(skill => skill.id))
}

function toggleCreateAgentSkill(skillId: number, checked: boolean) {
  const current = new Set(createAgentSkillIds.value)
  if (checked) current.add(skillId)
  else current.delete(skillId)
  createAgentSkillIds.value = [...current]
  createAgentContextTools.value = pruneContextTools(createAgentContextTools.value, createAgentSkillIds.value)
}

function toggleEditAgentSkill(skillId: number, checked: boolean) {
  const current = new Set(editAgentSkillIds.value)
  if (checked) current.add(skillId)
  else current.delete(skillId)
  editAgentSkillIds.value = [...current]
  editAgentContextTools.value = pruneContextTools(editAgentContextTools.value, editAgentSkillIds.value)
}

function selectedSkillContext(skillIds: number[]) {
  const selectedIds = new Set(skillIds)
  return activeSkills.value
    .filter(skill => selectedIds.has(skill.id))
    .map(skill => [
      `Skill: ${skill.name}`,
      `Description: ${skill.description || 'No description provided.'}`,
    ].join('\n'))
    .join('\n\n---\n\n')
}

// ── Context tools (the tools an agent runs before it reads a message) ──
//
// The pickable set is exactly what the selected skills provide, because a tool
// the agent cannot call would be refused by the API on save.
function providedContextTools(skillIds: number[]) {
  const selected = new Set(skillIds)
  const seen = new Set<number>()
  const options: { id: number; name: string; is_active: boolean }[] = []
  for (const skill of activeSkills.value) {
    if (!selected.has(skill.id)) continue
    for (const toolId of skill.tool_ids || []) {
      if (seen.has(toolId)) continue
      const tool = toolById.value[toolId]
      if (!tool) continue
      seen.add(toolId)
      options.push({ id: toolId, name: tool.name, is_active: tool.is_active })
    }
  }
  return options.sort((a, b) => a.name.localeCompare(b.name))
}

// Only tools that can actually run and are not already on the list are
// offered, so the picker cannot add one the run would skip or a duplicate.
function contextToolOptions(skillIds: number[], entries: AgentContextTool[]) {
  const chosen = new Set(entries.map(entry => entry.tool_id))
  return providedContextTools(skillIds).filter(tool => tool.is_active && !chosen.has(tool.id))
}

// Dropping a skill takes its tools out of the agent's reach, so the entries
// that used them go too. Inactive tools are kept: the run skips them, and the
// row says so.
function pruneContextTools(entries: AgentContextTool[], skillIds: number[]) {
  const provided = new Set(providedContextTools(skillIds).map(tool => tool.id))
  return entries.filter(entry => provided.has(entry.tool_id))
}

function addContextToolEntry(entries: AgentContextTool[], toolId: number | null, options: { id: number; name: string; is_active: boolean }[]) {
  if (toolId === null) return entries
  const tool = options.find(option => option.id === toolId)
  if (!tool || entries.some(entry => entry.tool_id === tool.id)) return entries
  return [...entries, {
    tool_id: tool.id,
    name: tool.name,
    comment: '',
    arguments: '',
    position: entries.length,
    is_active: tool.is_active,
  }]
}

function removeContextToolEntry(entries: AgentContextTool[], index: number) {
  return entries.filter((_, i) => i !== index)
}

function patchContextToolEntry(entries: AgentContextTool[], index: number, patch: Partial<AgentContextTool>) {
  return entries.map((entry, i) => (i === index ? { ...entry, ...patch } : entry))
}

// The tool's live active flag where it is known, so a tool deactivated after
// the entry was saved still shows as inactive.
function contextToolIsActive(entry: AgentContextTool) {
  return toolById.value[entry.tool_id]?.is_active ?? entry.is_active
}

// The API takes only the id, the comment and the arguments; the order of the
// list is the order the block is injected in.
function contextToolPayload(entries: AgentContextTool[]) {
  return entries.map(entry => ({
    tool_id: entry.tool_id,
    comment: (entry.comment || '').trim() || null,
    arguments: (entry.arguments || '').trim() || null,
  }))
}

function openCreate() {
  editingId.value = null
  projectForm.value = { name: '', description: '', is_active: true }
  showProjectModal.value = true
}

function openEdit(id: number) {
  const p = projects.value.find(x => x.id === id)
  if (!p) return
  editingId.value = id
  projectForm.value = { name: p.name, description: p.description || '', is_active: p.is_active }
  showProjectModal.value = true
}

async function saveProject() {
  try {
    if (!editingId.value) {
      const created = await createProject(projectForm.value)
      showProjectModal.value = false
      await loadProjects()
      // Auto-select the newly created project
      selectProject(created.id)
    } else {
      await api.put(`/admin/projects/${editingId.value}`, projectForm.value)
      showProjectModal.value = false
      await loadProjects()
    }
  } catch (e) {
    console.error('Failed to save project', e)
  }
}

async function deleteProject(id: number) {
  if (!confirm(t('admin.projects.delete_confirm') || 'Delete this project?')) return
  try {
    await api.delete(`/admin/projects/${id}`)
    if (selectedProjectId.value === id) {
      selectedProjectId.value = null
      selectedUserId.value = null
      selectedChatId.value = null
      projectAgents.value = []
      projectUsers.value = []
      userChats.value = []
      messages.value = []
    }
    await loadProjects()
  } catch (e) {
    console.error('Failed to delete project', e)
  }
}

function selectFirstProject() {
  if (projects.value.length > 0) {
    selectProject(projects.value[0].id, { auto: true })
  }
}

function selectProject(id: number, opts: { auto?: boolean } = {}) {
  disconnectChatSocket();
  selectedProjectId.value = id
  selectedUserId.value = null
  selectedChatId.value = null
  if (!opts.auto) mobilePane.value = 'project'
  projectAgents.value = []
  projectUsers.value = []
  projectTables.value = []
  userChats.value = []
  messages.value = []
  agentPage.value = 1
  agentPages.value = 1
  agentTotal.value = 0
  userPage.value = 1
  userPages.value = 1
  userTotal.value = 0
  tablePage.value = 1
  tablePages.value = 1
  tableTotal.value = 0
  selectedProjectTable.value = null
  tableDataRows.value = []
  tableDataPage.value = 1
  tableDataPages.value = 1
  tableDataTotal.value = 0
  tableDataSearch.value = ''
  loadProjectAgents()
  loadProjectUsers()
  loadProjectTables()
  reloadFlow()
}

async function loadProjectAgents() {
  if (!selectedProjectId.value) return
  loadingAgents.value = true
  try {
    const res = await api.get(`/admin/projects/${selectedProjectId.value}/agents`, {
      params: { search: agentSearch.value, page: agentPage.value, page_size: PROJECT_MEMBERS_PAGE_SIZE }
    })
    projectAgents.value = res.data.items
    agentTotal.value = res.data.total
    agentPages.value = res.data.pages
    if (projectAgents.value.length === 0 && agentPage.value > 1) {
      agentPage.value -= 1
      await loadProjectAgents()
      return
    }
  } catch (e) {
    console.error('Failed to load project agents', e)
  } finally {
    loadingAgents.value = false
  }
}

function changeAgentPage(page: number) {
  if (page < 1 || page > agentPages.value || page === agentPage.value) return
  agentPage.value = page
  loadProjectAgents()
}

let agentSearchTimer: ReturnType<typeof setTimeout> | null = null
watch(agentSearch, () => {
  if (agentSearchTimer) clearTimeout(agentSearchTimer)
  agentSearchTimer = setTimeout(() => {
    agentPage.value = 1
    loadProjectAgents()
  }, 300)
})

async function loadProjectUsers() {
  if (!selectedProjectId.value) return
  loadingUsers.value = true
  try {
    const res = await api.get(`/admin/projects/${selectedProjectId.value}/users`, {
      params: { search: userSearch.value, page: userPage.value, page_size: PROJECT_MEMBERS_PAGE_SIZE }
    })
    projectUsers.value = res.data.items
    userTotal.value = res.data.total
    userPages.value = res.data.pages
    if (projectUsers.value.length === 0 && userPage.value > 1) {
      userPage.value -= 1
      await loadProjectUsers()
      return
    }
    if (!selectedUserId.value && projectUsers.value.length > 0) {
      selectFirstUser()
    }
  } catch (e) {
    console.error('Failed to load project users', e)
  } finally {
    loadingUsers.value = false
  }
}

function changeUserPage(page: number) {
  if (page < 1 || page > userPages.value || page === userPage.value) return
  userPage.value = page
  loadProjectUsers()
}

let userSearchTimer: ReturnType<typeof setTimeout> | null = null
watch(userSearch, () => {
  if (userSearchTimer) clearTimeout(userSearchTimer)
  userSearchTimer = setTimeout(() => {
    userPage.value = 1
    loadProjectUsers()
  }, 300)
})

async function loadProjectTables() {
  if (!selectedProjectId.value) return
  loadingTables.value = true
  try {
    const res = await api.get(`/admin/projects/${selectedProjectId.value}/tables`, {
      params: { search: tableSearch.value, page: tablePage.value, page_size: PROJECT_MEMBERS_PAGE_SIZE }
    })
    projectTables.value = res.data.items
    tableTotal.value = res.data.total
    tablePages.value = res.data.pages
    if (projectTables.value.length === 0 && tablePage.value > 1) {
      tablePage.value -= 1
      await loadProjectTables()
      return
    }
  } catch (e) {
    console.error('Failed to load project tables', e)
  } finally {
    loadingTables.value = false
  }
}

function changeTablePage(page: number) {
  if (page < 1 || page > tablePages.value || page === tablePage.value) return
  tablePage.value = page
  loadProjectTables()
}

let tableSearchTimer: ReturnType<typeof setTimeout> | null = null
watch(tableSearch, () => {
  if (tableSearchTimer) clearTimeout(tableSearchTimer)
  tableSearchTimer = setTimeout(() => {
    tablePage.value = 1
    loadProjectTables()
  }, 300)
})

// --- Selected table data (like /admin/storage) ---
const selectedTableInfo = computed(() =>
  projectTables.value.find((table) => table.name === selectedProjectTable.value) || null,
)

const tableDataColumns = computed<StorageColumnInfo[]>(() =>
  (selectedTableInfo.value?.columns || []).filter(
    (column) => !['id', 'created_at', 'updated_at'].includes(column.name),
  ),
)

function tableColumnKind(column: StorageColumnInfo): string {
  const type = column.data_type.toLowerCase()
  if (type.includes('bool')) return 'boolean'
  if (type.includes('json')) return 'json'
  if (type.includes('timestamp') || type.includes('datetime')) return 'datetime'
  if (type === 'date') return 'date'
  if (type === 'time' || type.startsWith('time ')) return 'time'
  if (
    type.includes('int') ||
    type.includes('float') ||
    type.includes('numeric') ||
    type.includes('decimal') ||
    type.includes('double')
  ) {
    return 'number'
  }
  if (type.includes('text')) return 'longtext'
  return 'text'
}

function displayTableValue(value: any, column: StorageColumnInfo) {
  if (value === null || value === undefined || value === '') return '-'
  if (tableColumnKind(column) === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function formatTableDate(value: string | null) {
  if (!value) return ''
  return new Date(value).toLocaleString()
}

async function selectProjectTable(name: string) {
  // On a phone the rows live in their own pane, so picking a table has to
  // move the view to it or the tap would appear to do nothing.
  mobilePane.value = 'data'
  if (selectedProjectTable.value === name) return
  selectedProjectTable.value = name
  selectedTableDataRowIds.value = []
  tableDataPage.value = 1
  tableDataSearch.value = ''
  tableDataSortBy.value = 'id'
  tableDataSortDir.value = 'asc'
  await loadTableData()
}

async function loadTableData() {
  if (!selectedProjectTable.value) return
  loadingTableData.value = true
  try {
    const data = await fetchRows(selectedProjectTable.value, tableDataSearch.value, tableDataPage.value, 10, tableDataSortBy.value, tableDataSortDir.value)
    tableDataRows.value = data.items
    tableDataTotal.value = data.total
    tableDataPages.value = data.pages
    tableDataPage.value = data.page
  } catch (e) {
    console.error('Failed to load table data', e)
    tableDataRows.value = []
    tableDataTotal.value = 0
  } finally {
    loadingTableData.value = false
  }
}

function toggleTableDataSort(column: string) {
  if (tableDataSortBy.value === column) {
    tableDataSortDir.value = tableDataSortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    tableDataSortBy.value = column
    tableDataSortDir.value = 'asc'
  }
  tableDataPage.value = 1
  loadTableData()
}

function tableDataSortArrowPath(): string {
  return tableDataSortDir.value === 'desc' ? 'M5 9l7 7 7-7' : 'M5 15l7-7 7 7'
}

function changeTableDataPage(page: number) {
  if (page < 1 || page > tableDataPages.value || page === tableDataPage.value) return
  tableDataPage.value = page
  loadTableData()
}

let tableDataSearchTimer: ReturnType<typeof setTimeout> | null = null
watch(tableDataSearch, () => {
  if (tableDataSearchTimer) clearTimeout(tableDataSearchTimer)
  tableDataSearchTimer = setTimeout(() => {
    tableDataPage.value = 1
    loadTableData()
  }, 300)
})


// --- Row editing / export / import (like /admin/storage) ---
function showTableNotice(message: string) {
  tableNotice.value = message
  window.setTimeout(() => {
    if (tableNotice.value === message) tableNotice.value = ''
  }, 2400)
}

function tableErrorMessage(error: any, fallback: string) {
  return error?.response?.data?.detail || error?.message || fallback
}

function toFormTableValue(value: any, column: StorageColumnInfo): any {
  if (tableColumnKind(column) === 'json' && value !== null && typeof value === 'object') {
    return JSON.stringify(value, null, 2)
  }
  return value ?? ''
}

function fromFormTableValue(value: any, column: StorageColumnInfo): any {
  if (tableColumnKind(column) === 'json' && typeof value === 'string' && value.trim() !== '') {
    try {
      return JSON.parse(value)
    } catch {
      return value
    }
  }
  return value
}

function openCreateProjectRow() {
  editingProjectRowId.value = null
  projectRowData.value = Object.fromEntries(tableDataColumns.value.map((column) => [column.name, '']))
  projectRowError.value = ''
  showProjectRowModal.value = true
}

function openEditProjectRow(row: StorageRow) {
  editingProjectRowId.value = row.id
  projectRowData.value = Object.fromEntries(
    tableDataColumns.value.map((column) => [column.name, toFormTableValue(row.data[column.name], column)]),
  )
  projectRowError.value = ''
  showProjectRowModal.value = true
}

async function saveProjectRow() {
  if (!selectedProjectTable.value) return
  projectRowSaving.value = true
  projectRowError.value = ''
  try {
    const payload = Object.fromEntries(
      tableDataColumns.value.map((column) => [column.name, fromFormTableValue(projectRowData.value[column.name], column)]),
    )
    if (editingProjectRowId.value) {
      await updateRow(selectedProjectTable.value, editingProjectRowId.value, payload)
    } else {
      await createRow(selectedProjectTable.value, payload)
    }
    showProjectRowModal.value = false
    await loadTableData()
    showTableNotice(t('admin.storage.row_saved'))
  } catch (error: any) {
    projectRowError.value = tableErrorMessage(error, t('admin.storage.failed_save_row'))
  } finally {
    projectRowSaving.value = false
  }
}

async function removeProjectRow(row: StorageRow) {
  if (!selectedProjectTable.value) return
  if (!window.confirm(t('admin.storage.delete_row_confirm', { id: row.id }))) return
  try {
    await deleteRow(selectedProjectTable.value, row.id)
    if (tableDataRows.value.length === 1 && tableDataPage.value > 1) {
      tableDataPage.value -= 1
    }
    await loadTableData()
    showTableNotice(t('admin.storage.row_deleted'))
  } catch (error: any) {
    tableDataError.value = tableErrorMessage(error, t('admin.storage.failed_delete_row'))
  }
}

const allTableDataRowsSelected = computed(() =>
  tableDataRows.value.length > 0 && selectedTableDataRowIds.value.length === tableDataRows.value.length,
)

function toggleTableDataRow(rowId: number) {
  const index = selectedTableDataRowIds.value.indexOf(rowId)
  if (index >= 0) selectedTableDataRowIds.value.splice(index, 1)
  else selectedTableDataRowIds.value.push(rowId)
}

function toggleAllTableDataRows() {
  if (allTableDataRowsSelected.value) selectedTableDataRowIds.value = []
  else selectedTableDataRowIds.value = tableDataRows.value.map((row) => row.id)
}

async function bulkDeleteProjectRows() {
  if (!selectedProjectTable.value || selectedTableDataRowIds.value.length === 0) return
  const count = selectedTableDataRowIds.value.length
  if (!window.confirm(t('admin.storage.delete_selected_confirm', { count }))) return
  try {
    for (const rowId of [...selectedTableDataRowIds.value]) {
      await deleteRow(selectedProjectTable.value, rowId)
    }
    const removed = count
    selectedTableDataRowIds.value = []
    if (tableDataRows.value.length === removed && tableDataPage.value > 1) {
      tableDataPage.value -= 1
    }
    await loadTableData()
    showTableNotice(t('admin.storage.rows_deleted', { count: removed }))
  } catch (error: any) {
    tableDataError.value = tableErrorMessage(error, t('admin.storage.failed_delete_row'))
  }
}

async function handleProjectTableExport() {
  if (!selectedProjectTable.value || !selectedTableInfo.value) return
  try {
    const blob = await exportExcel(selectedProjectTable.value)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${selectedTableInfo.value.name}.xlsx`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error: any) {
    tableDataError.value = tableErrorMessage(error, t('admin.storage.failed_export'))
  }
}

async function onProjectExcelFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  excelFile.value = input.files?.[0] || null
  excelPreview.value = null
  importMapping.value = {}
  if (!selectedProjectTable.value || !excelFile.value) return
  previewingExcel.value = true
  tableDataError.value = ''
  try {
    const preview = await previewExcel(selectedProjectTable.value, excelFile.value)
    excelPreview.value = preview
    importMapping.value = { ...preview.suggested_mapping }
  } catch (error: any) {
    tableDataError.value = tableErrorMessage(error, t('admin.storage.failed_preview'))
  } finally {
    previewingExcel.value = false
  }
}

function projectSampleForHeader(header: string) {
  if (!excelPreview.value) return ''
  const index = excelPreview.value.headers.indexOf(header)
  if (index < 0) return ''
  const sample = excelPreview.value.sample_rows
    .map((row) => row[index])
    .find((value) => value !== null && value !== undefined && value !== '')
  return sample === undefined ? '' : String(sample)
}

async function handleProjectImport() {
  if (!selectedProjectTable.value || !excelFile.value) return
  const mapping = Object.fromEntries(
    Object.entries(importMapping.value).filter(([, excelColumn]) => Boolean(excelColumn)),
  )
  importing.value = true
  try {
    const result = await importExcel(selectedProjectTable.value, excelFile.value, mapping)
    showProjectImportModal.value = false
    resetProjectImportState()
    await loadTableData()
    showTableNotice(t('admin.storage.imported_rows', { count: result.imported }))
  } catch (error: any) {
    tableDataError.value = tableErrorMessage(error, t('admin.storage.failed_import'))
  } finally {
    importing.value = false
  }
}

function resetProjectImportState() {
  excelFile.value = null
  excelPreview.value = null
  importMapping.value = {}
  previewingExcel.value = false
}

function closeProjectImportModal() {
  showProjectImportModal.value = false
  resetProjectImportState()
}

function openEditProjectTable(table: StorageTableInfo) {
  editingProjectTableName.value = table.name
  projectTableName.value = table.name
  projectTableDescription.value = table.description || ''
  projectModalColumns.value = (table.columns || [])
    .filter((column) => !['id', 'created_at', 'updated_at'].includes(column.name))
    .map((column) => ({
      name: column.name,
      data_type: column.editor_type || 'string',
      description: column.description || '',
      length: column.length ?? null,
      nullable: column.nullable ?? true,
      default_value: column.default_value ?? null,
    }))
  projectTableError.value = ''
  showProjectTableModal.value = true
}

function addProjectColumn() {
  projectModalColumns.value.push({
    name: '',
    data_type: 'string',
    description: '',
    length: 255,
    nullable: true,
    default_value: null,
  })
}

function removeProjectColumn(index: number) {
  projectModalColumns.value.splice(index, 1)
}

async function saveProjectTable() {
  if (!projectTableName.value.trim()) {
    projectTableError.value = t('admin.storage.table_name_required')
    return
  }
  projectTableSaving.value = true
  projectTableError.value = ''
  try {
    const payload: StorageTableUpdate = {
      name: projectTableName.value,
      description: projectTableDescription.value,
      columns: projectModalColumns.value.map((column) => ({
        name: column.name,
        data_type: column.data_type,
        description: column.description,
        length: column.length,
        nullable: column.nullable,
        default_value: column.default_value === '' ? null : column.default_value,
      })),
    }
    if (editingProjectTableName.value) {
      await updateTable(editingProjectTableName.value, payload)
    }
    showProjectTableModal.value = false
    if (selectedProjectTable.value === editingProjectTableName.value) {
      selectedProjectTable.value = projectTableName.value
    }
    await loadProjectTables()
    if (selectedProjectTable.value === projectTableName.value) {
      await loadTableData()
    }
    showTableNotice(t('admin.storage.table_saved'))
  } catch (error: any) {
    projectTableError.value = tableErrorMessage(error, t('admin.storage.failed_save_table'))
  } finally {
    projectTableSaving.value = false
  }
}

function selectFirstUser() {
  if (projectUsers.value.length > 0) {
    selectUser(projectUsers.value[0].id, { auto: true })
  }
}

function selectUser(id: number, opts: { auto?: boolean } = {}) {
  disconnectChatSocket();
  selectedUserId.value = id
  selectedChatId.value = null
  if (!opts.auto) mobilePane.value = 'chats'
  messages.value = []
  loadUserChats()
}

function selectFirstChat() {
  if (userChats.value.length > 0) {
    selectChat(userChats.value[0].id, { auto: true })
  }
}

async function loadUserChats() {
  if (!selectedProjectId.value || !selectedUserId.value) return
  loadingChats.value = true
  try {
    userChats.value = await fetchAdminUserChats(selectedProjectId.value, selectedUserId.value)
    if (!selectedChatId.value && userChats.value.length > 0) {
      selectFirstChat()
    }
  } catch (e) {
    console.error('Failed to load chats', e)
  } finally {
    loadingChats.value = false
  }
}

async function selectChat(id: number, opts: { auto?: boolean } = {}) {
  disconnectChatSocket();
  selectedChatId.value = id
  if (!opts.auto) mobilePane.value = 'chat'
  const chat = userChats.value.find(c => c.id === id)
  selectedChatDescription.value = chat?.description || ''
  chatLoading.value = true
  clickedChatId.value = id
  try {
    await loadChatMessages(id)
  } finally {
    chatLoading.value = false
    clickedChatId.value = null
  }
  connectChatSocket()
  scrollToBottom()
}

async function sendMessageAction() {
  if (agentLoopRunning.value) {
    stopAgentLoop()
    return
  }
  const content = newMessageContent.value.trim()
  if (!content || !selectedProjectId.value || !selectedChatId.value) return

  sending.value = true
  try {
    // Save workflow before sending so the agent assignments are current
    // await saveFlow();
    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
      agentLoopRunning.value = true
      chatSocket.send(JSON.stringify({ type: 'message', content }))
      newMessageContent.value = ''
    } else {
      // HTTP fallback
      await sendAdminChatMessage(selectedProjectId.value, selectedUserId.value, selectedChatId.value, {
        content,
        sender_type: 'user',
      })
      newMessageContent.value = ''
      await loadMessages()
    }
  } catch (e) {
    console.error('Failed to send message', e)
  } finally {
    sending.value = false
  }
}

function stopAgentLoop() {
  if (!agentLoopRunning.value || agentLoopStopping.value) return
  agentLoopStopping.value = true
  if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
    chatSocket.send(JSON.stringify({ type: 'stop_agent_loop' }))
  }
}

async function createChatAction() {
  if (!selectedProjectId.value || !selectedUserId.value || !createChatDescription.value.trim()) return
  try {
    const chat = await createAdminChat(selectedProjectId.value, selectedUserId.value, createChatDescription.value.trim())
    createChatDescription.value = ''
    showCreateChatModal.value = false
    await loadUserChats()
    selectChat(chat.id)
  } catch (e) {
    console.error('Failed to create chat', e)
  }
}

// Remove user from project (detach)
async function removeUser(userId: number) {
  if (!selectedProjectId.value) return
  try {
    await api.delete(`/admin/projects/${selectedProjectId.value}/users/${userId}`)
    if (selectedUserId.value === userId) {
      selectedUserId.value = null
      selectedChatId.value = null
      userChats.value = []
      messages.value = []
    }
    await loadProjectUsers()
  } catch (e) {
    console.error('Failed to remove user', e)
  }
}

// Remove agent from project (detach)
async function removeAgent(agentId: number) {
  if (!selectedProjectId.value) return
  try {
    await api.delete(`/admin/projects/${selectedProjectId.value}/agents/${agentId}`)
    await loadProjectAgents()
  } catch (e) {
    console.error('Failed to remove agent', e)
  }
}

// Remove table from project (unassign; the table itself is kept)
async function removeProjectTable(table: StorageTableInfo) {
  if (!selectedProjectId.value) return
  if (!window.confirm(t('admin.storage.unassign_confirm', { name: table.name }))) return
  try {
    await api.delete(`/admin/projects/${selectedProjectId.value}/tables/${encodeURIComponent(table.name)}`)
    if (selectedProjectTable.value === table.name) {
      selectedProjectTable.value = null
      tableDataRows.value = []
      tableDataTotal.value = 0
    }
    await loadProjectTables()
    showTableNotice(t('admin.storage.table_unassigned'))
  } catch (e) {
    console.error('Failed to remove table from project', e)
    showTableNotice(t('admin.storage.failed_unassign_table'))
  }
}

// Delete agent entirely (permanent, not just detach)
async function deleteAgent(agentId: number) {
  if (!confirm(t('admin.agents.delete_confirm'))) return
  try {
    await api.delete(`/admin/agents/${agentId}`)
    await loadProjectAgents()
  } catch (e) {
    console.error('Failed to delete agent', e)
  }
}

// Edit agent (open modal)
async function editAgent(agentId: number) {
  try {
    if (activeSkills.value.length === 0) await loadActiveSkills()
    const res = await api.get(`/admin/agents/${agentId}`)
    const agent = res.data
    editAgentId.value = agent.id
    editAgentName.value = agent.name
    editAgentDescription.value = agent.description || ''
    editAgentIsActive.value = agent.is_active !== false
    const allowedSkillIds = activeSkillIds()
    editAgentSkillIds.value = [...(agent.skill_ids || [])].filter(skillId => allowedSkillIds.has(skillId))
    editAgentContextTools.value = [...(agent.context_tools || [])]
      .sort((a, b) => a.position - b.position)
      .map(entry => ({ ...entry, comment: entry.comment || '', arguments: entry.arguments || '' }))
    editContextToolToAdd.value = null
    editAgentGeneratorPrompt.value = ''
    showAgentEditModal.value = true
  } catch (e) {
    console.error('Failed to load agent', e)
  }
}

async function updateAgent() {
  if (!editAgentId.value) return
  try {
    await api.put(`/admin/agents/${editAgentId.value}`, {
      name: editAgentName.value,
      description: editAgentDescription.value,
      skill_ids: editAgentSkillIds.value,
      context_tools: contextToolPayload(editAgentContextTools.value),
      is_active: editAgentIsActive.value,
    })
    showAgentEditModal.value = false
    editAgentId.value = null
    await loadProjectAgents()
    await loadAgentTools()
  } catch (e) {
    console.error('Failed to update agent', e)
  }
}

function openCreateAgentModal() {
  createAgentName.value = ''
  createAgentDescription.value = ''
  createAgentSkillIds.value = []
  createAgentGeneratorPrompt.value = ''
  createAgentContextTools.value = []
  createContextToolToAdd.value = null
  showCreateAgentModal.value = true
  if (activeSkills.value.length === 0) loadActiveSkills()
}

async function generateCreateAgentFields() {
  generatingAgent.value = true
  try {
    const prompt = [
      createAgentGeneratorPrompt.value.trim(),
      'Generate fields for an agent create form.',
      'The description field will be used directly as the agent system prompt at runtime.',
      'Use the selected active skills as the agent capability context.',
      'Generate behavior instructions, not marketing copy.',
      '',
      'Selected skills:',
      selectedSkillContext(createAgentSkillIds.value) || 'No skills selected.',
      '',
      'Use the following structure for your response:',
    ].join('\n')
    const structure = {
      name: createAgentName.value + '. Create a concise agent name, usually 2-4 words, that clearly describes the agent role.',
      description: createAgentDescription.value + '. Create a detailed Markdown system prompt for this agent. Include role, mission, responsibilities, how and when to use assigned skills/tools, response style, constraints, what not to do, and failure behavior. The prompt must be directly usable as SystemMessage content.',
    }
    const generated = await generateJson(prompt, structure)
    createAgentName.value = typeof generated.name === 'string' ? generated.name : createAgentName.value
    createAgentDescription.value = typeof generated.description === 'string' ? generated.description : createAgentDescription.value
  } catch (e) {
    console.error('Failed to generate agent', e)
  } finally {
    generatingAgent.value = false
  }
}

async function generateEditAgentFields() {
  generatingAgent.value = true
  try {
    const prompt = [
      editAgentGeneratorPrompt.value.trim(),
      'Generate fields for an agent edit form.',
      'Use the selected active skills as the agent capability context.',
      '',
      'Selected skills:',
      selectedSkillContext(editAgentSkillIds.value) || 'No skills selected.',
      '',
      'Use the following structure for your response:',
    ].join('\n')
    const structure = {
      name: editAgentName.value + '. The name should be concise and describe the agent role.',
      description: editAgentDescription.value + '. Describe what this agent does and how it uses the selected skills.',
    }
    const generated = await generateJson(prompt, structure)
    editAgentName.value = typeof generated.name === 'string' ? generated.name : editAgentName.value
    editAgentDescription.value = typeof generated.description === 'string' ? generated.description : editAgentDescription.value
  } catch (e) {
    console.error('Failed to generate agent', e)
  } finally {
    generatingAgent.value = false
  }
}

// Edit chat description
async function editChatDescription(chatId: number) {
  try {
    const res = await api.get(`/admin/projects/${selectedProjectId.value}/users/${selectedUserId.value}/chats/${chatId}`)
    const chat = res.data
    editingChatId.value = chat.id
    chatForm.value = { description: chat.description || '' }
    selectedChatId.value = chat.id
    selectedChatDescription.value = chat.description || ''
    showChatModal.value = true
  } catch (e) {
    console.error('Failed to load chat', e)
  }
}

async function updateChatDescription() {
  if (!editingChatId.value) return
  try {
    await api.put(`/admin/projects/${selectedProjectId.value}/users/${selectedUserId.value}/chats/${editingChatId.value}`, {
      description: chatForm.value.description,
    })
    showChatModal.value = false
    editingChatId.value = null
    selectedChatDescription.value = chatForm.value.description
    await loadUserChats()
  } catch (e) {
    console.error('Failed to update chat', e)
  }
}

// Delete chat
async function deleteChat(chatId: number) {
  if (!confirm(t('admin.chat.delete_confirm') || 'Delete this chat?')) return
  try {
   
    await api.delete(`/admin/projects/${selectedProjectId.value}/users/${selectedUserId.value}/chats/${chatId}`)
    disconnectChatSocket()
    if (selectedChatId.value === chatId) {
      selectedChatId.value = null
      selectedChatDescription.value = ''
      messages.value = []
    }
    await loadUserChats()
  } catch (e) {
    console.error('Failed to delete chat', e)
  }
}

// Create agent
async function createAgentAction() {
  if (!createAgentName.value.trim() || !selectedProjectId.value) return
  try {
    const res = await api.post('/admin/agents', {
      name: createAgentName.value.trim(),
      description: createAgentDescription.value.trim(),
      skill_ids: createAgentSkillIds.value,
      context_tools: contextToolPayload(createAgentContextTools.value),
    })
    // Assign to current project
    await api.post(`/admin/projects/${selectedProjectId.value}/agents/${res.data.id}`)
    createAgentName.value = ''
    createAgentDescription.value = ''
    createAgentSkillIds.value = []
    createAgentGeneratorPrompt.value = ''
    createAgentContextTools.value = []
    createContextToolToAdd.value = null
    showCreateAgentModal.value = false
    await loadProjectAgents()
    await loadAgentTools()
  } catch (e) {
    console.error('Failed to create agent', e)
  }
}

// ── Scroll ──
const messagesRef = ref<HTMLElement | null>(null)
let chatSocket: WebSocket | null = null
function scrollToBottom() {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

// A chat opens on its newest page and the rest of the history arrives only if
// the reader scrolls up. Ten bubbles fill the panel, and the newest page is
// what almost every visit wants, so a long conversation is no longer fetched
// whole just to render its last line.
const MESSAGES_PAGE_SIZE = 10
const MIN_VISIBLE_MESSAGES = 10
const hasMoreMessages = ref(false)
const loadingOlderMessages = ref(false)

async function loadChatMessages(chatId: number) {
  const projectId = selectedProjectId.value
  const userId = selectedUserId.value
  if (projectId == null || userId == null) return
  loadingMessages.value = true
  hasMoreMessages.value = false
  try {
    const page = await fetchAdminChatMessages(projectId, userId, chatId, {
      limit: MESSAGES_PAGE_SIZE,
      includeDebug: debugMode.value,
    })
    // The reader may have picked another chat while this was in flight.
    if (selectedChatId.value !== chatId) return
    messages.value = page.messages
    hasMoreMessages.value = page.has_more
    await nextTick()
    await fillVisibleMessages()
  } catch (e) {
    console.error('Failed to load messages', e)
  } finally {
    if (selectedChatId.value === chatId) loadingMessages.value = false
  }
}

// With debug mode off the server drops tool and flow rows, but agent-to-agent
// traffic still fails the participant test, so a page can leave the panel
// empty. Keep pulling until the conversation itself has something to show, and
// stop after a bounded number of pages so a chat of pure tool traffic cannot
// loop forever.
async function fillVisibleMessages() {
  let guard = 0
  while (hasMoreMessages.value && visibleMessages.value.length < MIN_VISIBLE_MESSAGES && guard < 20) {
    guard += 1
    const loaded = messages.value.length
    await loadOlderMessages()
    if (messages.value.length === loaded) break
  }
}

async function loadOlderMessages() {
  const chatId = selectedChatId.value
  const projectId = selectedProjectId.value
  const userId = selectedUserId.value
  const oldestId = messages.value[0]?.id
  if (loadingOlderMessages.value || !hasMoreMessages.value) return
  if (chatId == null || projectId == null || userId == null || oldestId == null) return

  const container = messagesRef.value
  // Prepending grows the scroller upwards. Remember where it was so the reader
  // keeps looking at the same bubble instead of being thrown to the new top.
  const previousHeight = container?.scrollHeight ?? 0
  const previousTop = container?.scrollTop ?? 0
  loadingOlderMessages.value = true
  try {
    const page = await fetchAdminChatMessages(projectId, userId, chatId, {
      limit: MESSAGES_PAGE_SIZE,
      beforeId: oldestId,
      includeDebug: debugMode.value,
    })
    if (selectedChatId.value !== chatId) return
    hasMoreMessages.value = page.has_more
    const known = new Set(messages.value.map((msg) => msg.id))
    const older = page.messages.filter((msg) => !known.has(msg.id))
    if (older.length === 0) return
    messages.value = [...older, ...messages.value]
    await nextTick()
    if (container) container.scrollTop = previousTop + (container.scrollHeight - previousHeight)
  } catch (e) {
    console.error('Failed to load older messages', e)
  } finally {
    loadingOlderMessages.value = false
  }
}

function onMessagesScroll() {
  const container = messagesRef.value
  if (!container) return
  // Only the top edge pulls history in; everything else is ordinary scrolling.
  if (container.scrollTop <= 80) loadOlderMessages()
}

// In normal mode the debug rows never leave the server, so flipping the switch
// has to refetch the conversation instead of re-filtering what is loaded.
watch(debugMode, async () => {
  const chatId = selectedChatId.value
  if (!chatId) return
  await loadChatMessages(chatId)
  scrollToBottom()
})
// Safety timeout for loading states
watch(chatLoading, (val) => {
  if (val) {
    setTimeout(() => { chatLoading.value = false; clickedChatId.value = null; }, 10000)
  }
})

// ── Fetch available members ──

function activeMemberModalType(): 'agent' | 'user' | 'table' {
  if (showAddAgentModal.value) return 'agent'
  if (showAddUserModal.value) return 'user'
  return 'table'
}

async function fetchAvailableMembers(type: 'agent' | 'user' | 'table') {
  if (!selectedProjectId.value) return
  loadingAvailable.value = true
  try {
    const tab = type === 'agent' ? 'available-agents' : type === 'table' ? 'available-tables' : 'available-users'
    const res = await api.get(`/admin/projects/${selectedProjectId.value}/${tab}`, {
      params: { search: memberSearch.value, page: memberPage.value, page_size: PROJECT_MEMBERS_PAGE_SIZE }
    })
    availableMembers.value = res.data.items
    memberTotal.value = res.data.total
    memberPages.value = res.data.pages
    if (availableMembers.value.length === 0 && memberPage.value > 1) {
      memberPage.value -= 1
      await fetchAvailableMembers(type)
      return
    }
  } catch (e) {
    console.error('Failed to fetch available members', e)
    availableMembers.value = []
  } finally {
    loadingAvailable.value = false
  }
}

function changeMemberPage(page: number) {
  if (page < 1 || page > memberPages.value || page === memberPage.value) return
  memberPage.value = page
  fetchAvailableMembers(activeMemberModalType())
}

function openAddAgent() {
  memberSearch.value = ''
  availableMembers.value = []
  memberPage.value = 1
  memberPages.value = 1
  memberTotal.value = 0
  showAddAgentModal.value = true
  fetchAvailableMembers('agent')
}

function openAddUser() {
  memberSearch.value = ''
  availableMembers.value = []
  memberPage.value = 1
  memberPages.value = 1
  memberTotal.value = 0
  showAddUserModal.value = true
  fetchAvailableMembers('user')
}

function openAddTable() {
  memberSearch.value = ''
  availableMembers.value = []
  memberPage.value = 1
  memberPages.value = 1
  memberTotal.value = 0
  showAddTableModal.value = true
  fetchAvailableMembers('table')
}

watch(memberSearch, () => {
  memberPage.value = 1
  if (showAddAgentModal.value) fetchAvailableMembers('agent')
  else if (showAddUserModal.value) fetchAvailableMembers('user')
  else if (showAddTableModal.value) fetchAvailableMembers('table')
})

async function assignMember(member: any, type: 'agent' | 'user' | 'table') {
  if (!selectedProjectId.value) return
  const tab = type === 'agent' ? 'agents' : type === 'table' ? 'tables' : 'users'
  try {
    await api.post(`/admin/projects/${selectedProjectId.value}/${tab}/${type === 'table' ? encodeURIComponent(member.name) : member.id}`)
    if (type === 'user') {
      await loadProjectUsers()
      selectFirstUser()
    } else if (type === 'table') {
      await loadProjectTables()
    } else {
      await loadProjectAgents()
    }
    await fetchAvailableMembers(type)
  } catch (e) {
    console.error('Failed to assign member', e)
  }
}

// ── Polling ──
let pollInterval: ReturnType<typeof setInterval> | null = null
async function fetchNewMessages() {
  if (!selectedChatId.value) return
  try {
    const { messages: msgs } = await fetchMessages(selectedChatId.value)
    // Append only what is missing: replacing the array would throw away the
    // older pages the reader has scrolled up to load.
    const known = new Set(messages.value.map((msg) => msg.id))
    const fresh = msgs.filter((msg) => !known.has(msg.id))
    if (fresh.length > 0) {
      messages.value = [...messages.value, ...fresh]
      nextTick(scrollToBottom)
    }
  } catch {}
}
</script>
<template>
  <div class="projects-layout">
    <!-- Phone-only step bar: below 768px the columns are shown one at a time,
         so this carries the way back and the switch between the project's
         setup panes and its workflow canvas. Inert on wider screens. -->
    <div class="mobile-stepbar" v-if="selectedProjectId && mobilePane !== 'projects'">
      <button type="button" class="mobile-step-back" @click="mobileBack">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" style="width:0.85rem;height:0.85rem"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" /></svg>
        <span>{{ mobileBackLabel }}</span>
      </button>
      <div class="mobile-step-tabs" v-if="isProjectPane">
        <button type="button" :class="{ 'is-active': mobilePane === 'project' }" @click="mobilePane = 'project'">
          {{ t('admin.sidebar.users') }}
        </button>
        <button type="button" :class="{ 'is-active': mobilePane === 'workflow' }" @click="mobilePane = 'workflow'">
          {{ t('admin.workflow.title') }}
        </button>
        <button v-if="selectedProjectTable" type="button" :class="{ 'is-active': mobilePane === 'data' }" @click="mobilePane = 'data'">
          {{ t('admin.storage.data') }}
        </button>
      </div>
    </div>
    <!-- â•â•â• COL 1: Projects List â•â•â• -->
    <div class="projects-col" :class="{ 'mobile-pane-hidden': mobilePane !== 'projects' }">
      <div class="projects-panel">
        <div class="projects-panel-header">
          <div class="projects-panel-title-row">
            <h3 class="projects-panel-title">{{ t('admin.sidebar.projects') }}</h3>
            <button @click="openCreate" class="projects-add-btn">{{ t('admin.projects.create') }}</button>
          </div>
          <div class="projects-search-row">
            <input type="search" v-model="projectSearch" class="projects-search"
              :placeholder="t('admin.projects.search_placeholder')" />
          </div>
        </div>
        <div class="projects-list">
          <template v-if="!loadingProjects">
            <div v-for="p in filteredProjects" :key="p.id"
              class="projects-item-wrapper"
              :class="{ 'projects-item-selected': selectedProjectId === p.id }"
              @click="selectProject(p.id)">
              <div class="projects-item-content">
                <div class="projects-item-name">
                  {{ p.name }}
                  <span v-if="p.is_system" class="projects-system-badge">{{ t('admin.projects.system_project') }}</span>
                </div>
                <div v-if="p.description" class="projects-item-meta">
                  <span class="projects-item-desc">{{ p.description.substring(0, 80) }}</span>
                </div>
              </div>
              <div class="projects-item-actions">
                <!-- The system project's row is refused by the API, so it is not
                     offered here either: only its badge shows what it is. -->
                <button v-if="!p.is_system" @click.stop="openEdit(p.id)" class="projects-action-btn" :title="t('admin.common.edit')">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" /></svg>
                </button>
                <button v-if="!p.is_system" @click.stop="deleteProject(p.id)" class="projects-action-btn projects-action-btn-danger" :title="t('admin.common.delete')">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg>
                </button>
              </div>
            </div>
            <div v-if="projects.length === 0" class="projects-empty">{{ t('admin.projects.no_projects') }}</div>
          </template>
          <div v-else class="loading-overlay loading-active">
            <div class="loading-spinner"></div>
            <span class="loading-text">{{ t('admin.projects.loading') }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- â•â•â• COL 2: Agents + Users + Tables â•â•â• -->
    <div class="projects-col" :class="{ 'projects-col-hidden': !selectedProjectId, 'mobile-pane-hidden': mobilePane !== 'project' }"
         style="display:flex;flex-direction:column;gap:0.5rem;overflow:hidden">

      <!-- Agents panel -->
      <div class="projects-panel" v-if="selectedProjectId" style="flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden">
        <div class="projects-panel-header">
          <div class="projects-panel-title-row">
            <h3 class="projects-panel-title">{{ t('admin.agents.title') }}</h3>
            <div style="display:flex;gap:0.25rem">
              <button @click="openCreateAgentModal" class="projects-add-btn">{{ t('admin.agents.new') }}</button>
              <button @click="openAddAgent()" class="projects-add-btn">{{ t('admin.agents.assign') }}</button>
            </div>
          </div>
          <div class="projects-search-row">
            <input type="search" v-model="agentSearch" class="projects-search" :placeholder="t('admin.agents.search')" />
          </div>
        </div>
        <div class="projects-list" style="flex:1;overflow-y:auto">
          <template v-if="!loadingAgents">
            <div v-for="a in projectAgents" :key="a.id" class="projects-item-wrapper" draggable="true" @dragstart="onAgentDragStart($event, a)" @click="editAgent(a.id)">
              <div class="projects-item-content">
                <div class="projects-item-name">{{ a.name }}</div>
                <div v-if="a.description" class="projects-item-meta">
                  <span class="projects-item-desc">{{ a.description.substring(0, 200) }}</span>
                </div>
              </div>
              <div class="projects-item-actions">
                <button @click.stop="removeAgent(a.id)" class="projects-action-btn" :title="t('admin.assign_member.remove')">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>
                </button>
                <button @click.stop="deleteAgent(a.id)" class="projects-action-btn projects-action-btn-danger" :title="t('admin.agents.delete')">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg>
                </button>
              </div>
            </div>
            <div v-if="projectAgents.length === 0" class="projects-empty">{{ t('admin.agents.no_agents') }}</div>
          </template>
          <div v-else class="loading-overlay loading-active">
            <div class="loading-spinner"></div>
            <span class="loading-text">{{ t('admin.projects.loading') }}</span>
          </div>
        </div>

        <div v-if="agentTotal > 0" class="projects-pagination">
          <span class="projects-page-total">{{ t('admin.storage.total_rows', { total: agentTotal }) }}</span>
          <template v-if="agentPages > 1">
            <button class="projects-page-btn" :disabled="agentPage <= 1" @click="changeAgentPage(agentPage - 1)">{{ t('admin.storage.prev_page') }}</button>
            <span class="projects-page-info">{{ t('admin.storage.page_x_of_y', { page: agentPage, pages: agentPages }) }}</span>
            <button class="projects-page-btn" :disabled="agentPage >= agentPages" @click="changeAgentPage(agentPage + 1)">{{ t('admin.storage.next_page') }}</button>
          </template>
        </div>
      </div>

      <!-- Users panel -->
      <div class="projects-panel" v-if="selectedProjectId" style="flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden">
        <div class="projects-panel-header">
          <div class="projects-panel-title-row">
            <h3 class="projects-panel-title">{{ t('admin.sidebar.users') }}</h3>
            <button @click="openAddUser()" class="projects-add-btn">{{ t('admin.users.assign') }}</button>
          </div>
          <div class="projects-search-row">
            <input type="search" v-model="userSearch" class="projects-search" :placeholder="t('admin.users.search')" />
          </div>
        </div>
        <div class="projects-list" style="flex:1;overflow-y:auto">
          <template v-if="!loadingUsers">
            <div v-for="u in projectUsers" :key="u.id"
              class="projects-item-wrapper"
              :class="{ 'projects-item-selected': selectedUserId === u.id }"
              @click="selectUser(u.id)">
              <div class="projects-item-content">
                <div class="projects-item-name">{{ u.name }}</div>
                <div v-if="u.email" class="projects-item-meta">
                  <span class="projects-item-desc">{{ u.email }}</span>
                </div>
              </div>
              <div class="projects-item-actions">
                <button @click.stop="removeUser(u.id)" class="projects-action-btn projects-action-btn-danger" :title="t('admin.assign_member.remove')">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>
                </button>
              </div>
            </div>
            <div v-if="projectUsers.length === 0" class="projects-empty">{{ t('admin.users.no_users') }}</div>
          </template>
          <div v-else class="loading-overlay loading-active">
            <div class="loading-spinner"></div>
            <span class="loading-text">{{ t('admin.projects.loading') }}</span>
          </div>
        </div>

        <div v-if="userTotal > 0" class="projects-pagination">
          <span class="projects-page-total">{{ t('admin.storage.total_rows', { total: userTotal }) }}</span>
          <template v-if="userPages > 1">
            <button class="projects-page-btn" :disabled="userPage <= 1" @click="changeUserPage(userPage - 1)">{{ t('admin.storage.prev_page') }}</button>
            <span class="projects-page-info">{{ t('admin.storage.page_x_of_y', { page: userPage, pages: userPages }) }}</span>
            <button class="projects-page-btn" :disabled="userPage >= userPages" @click="changeUserPage(userPage + 1)">{{ t('admin.storage.next_page') }}</button>
          </template>
        </div>
      </div>
      <!-- Tables panel -->
      <div class="projects-panel" v-if="selectedProjectId" style="flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden">
        <div class="projects-panel-header">
          <div class="projects-panel-title-row">
            <h3 class="projects-panel-title">{{ t('admin.storage.tables') }}</h3>
            <button @click="openAddTable()" class="projects-add-btn">{{ t('admin.storage.assign_project') }}</button>
          </div>
          <div class="projects-search-row">
            <input type="search" v-model="tableSearch" class="projects-search" :placeholder="t('admin.storage.search_tables')" />
          </div>
        </div>
        <div class="projects-list" style="flex:1;overflow-y:auto">
          <template v-if="!loadingTables">
            <div v-for="table in projectTables" :key="table.name" class="projects-item-wrapper"
                 :class="{ 'projects-item-selected': selectedProjectTable === table.name }"
                 @click="selectProjectTable(table.name)">
              <div class="projects-item-content">
                <div class="projects-item-name">{{ table.name }}</div>
                <div v-if="table.description" class="projects-item-meta">
                  <span class="projects-item-desc">{{ table.description }}</span>
                </div>
                <div class="projects-item-meta">
                  <span class="projects-item-desc">{{ table.columns.length }} {{ t('admin.storage.columns').toLowerCase() }} &middot; {{ t('admin.storage.total_rows', { total: table.row_count }) }}</span>
                </div>
                <div v-if="table.projects && table.projects.length" class="projects-project-badges">
                  <span v-for="project in table.projects" :key="project.id" class="projects-project-badge">{{ project.name }}</span>
                </div>
                <span v-if="table.is_system" class="projects-system-badge">
                  <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                  {{ t('admin.storage.system_table') }}
                </span>
              </div>
              <div class="projects-item-actions">
                <button v-if="!table.is_system" @click.stop="openEditProjectTable(table)" class="projects-action-btn" :title="t('admin.common.edit')">
                  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button @click.stop="removeProjectTable(table)" class="projects-action-btn projects-action-btn-danger" :title="t('admin.storage.remove_project')">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>
                </button>
              </div>
            </div>
            <div v-if="projectTables.length === 0" class="projects-empty">{{ t('admin.storage.no_tables') }}</div>
          </template>
          <div v-else class="loading-overlay loading-active">
            <div class="loading-spinner"></div>
            <span class="loading-text">{{ t('admin.projects.loading') }}</span>
          </div>
        </div>

        <div v-if="tableTotal > 0" class="projects-pagination">
          <span class="projects-page-total">{{ t('admin.storage.total_rows', { total: tableTotal }) }}</span>
          <template v-if="tablePages > 1">
            <button class="projects-page-btn" :disabled="tablePage <= 1" @click="changeTablePage(tablePage - 1)">{{ t('admin.storage.prev_page') }}</button>
            <span class="projects-page-info">{{ t('admin.storage.page_x_of_y', { page: tablePage, pages: tablePages }) }}</span>
            <button class="projects-page-btn" :disabled="tablePage >= tablePages" @click="changeTablePage(tablePage + 1)">{{ t('admin.storage.next_page') }}</button>
          </template>
        </div>
      </div>
    </div>

    <!-- â•â•â• COL 3: Workflow â•â•â• -->
    <div class="projects-col projects-col-flow" v-if="selectedProjectId" :class="{ 'mobile-pane-hidden': mobilePane !== 'workflow' && mobilePane !== 'data' }">
      <div class="projects-panel projects-panel-flow" :class="{ 'mobile-pane-hidden': mobilePane === 'data' }">
        <div class="projects-panel-header flow-header">
          <div class="projects-panel-title-row">
            <h3 class="projects-panel-title">{{ t('admin.workflow.title') }}</h3>
            <div class="flow-toolbar">
              <button class="flow-btn flow-btn-add" :title="t('admin.workflow.add_group')" @click="addFlowGroup">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>
              </button>
              <button class="flow-btn flow-btn-reload" :title="t('admin.workflow.reload')" @click="reloadFlow" :disabled="reloadingWorkflow">
                <svg x-show="!reloadingWorkflow" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" /></svg>
                <svg v-show="reloadingWorkflow" class="loading-spinner-sm" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" style="width:1rem;height:1rem"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" opacity="0.25"/><path fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
              </button>
              <button class="flow-btn flow-btn-save" :title="t('admin.common.save')" @click="saveFlow" :disabled="savingWorkflow">
                <svg v-show="!savingWorkflow" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="M10.125 2.25h-4.5c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125v-9M10.125 2.25h.375a9 9 0 0 1 9 9v.375M10.125 2.25A3.375 3.375 0 0 1 13.5 5.625v1.5c0 .621.504 1.125 1.125 1.125h1.5a3.375 3.375 0 0 1 3.375 3.375M9 15l2.25 2.25L15 12" /></svg>
                <svg v-show="savingWorkflow" class="loading-spinner-sm" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" style="width:1rem;height:1rem"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" opacity="0.25"/><path fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
              </button>
              <span class="flow-separator"></span>
              <button class="flow-btn" :title="t('admin.workflow.zoom_out')" @click="flowZoomOut">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607zM15.75 10.5h-7.5" /></svg>
              </button>
              <span class="flow-zoom-level">{{ flowZoomPercent }}</span>
              <button class="flow-btn" :title="t('admin.workflow.zoom_in')" @click="flowZoomIn">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607zM15.75 10.5h-1.5M10.5 10.5v-1.5m0 1.5h-1.5m1.5 0v1.5m0-1.5h1.5" /></svg>
              </button>
              <button class="flow-btn" :title="t('admin.workflow.reset_zoom')" @click="flowZoomReset">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="M9 9V4.5M9 9H4.5m0 0l3.75-3.75a9 9 0 01-3.75 3.75zM15 15V19.5M15 15h4.5m0 0l-3.75 3.75A9 9 0 0015 15z" /></svg>
              </button>
            </div>
          </div>
        </div>
        <div class="flow-canvas" ref="flowCanvas" @dragover.prevent @drop="onFlowDrop">
          <div v-if="loadingWorkflow" class="flow-loading-overlay">
            <div class="flow-loading-spinner"></div>
          </div>
          <!-- Gradients, shadows and the arrowhead are rebuilt by
               FlowBuilder.ensureDefs(), since render() replaces every child. -->
          <svg v-else class="flow-svg" ref="flowSvg"></svg>
        </div>
      </div>

      <!-- Table data panel (selected table, like /admin/storage) -->
      <div v-if="selectedProjectTable" class="projects-panel projects-panel-tabledata" :class="{ 'mobile-pane-hidden': mobilePane === 'workflow' }">
        <div class="projects-panel-header">
          <div class="projects-panel-title-row">
            <h3 class="projects-panel-title">{{ selectedProjectTable }} {{ t('admin.storage.data') }}</h3>
            <div class="projects-data-toolbar">
              <button class="projects-data-btn" :disabled="loadingTableData" :title="t('admin.storage.reload')" @click="loadTableData">
                <svg v-show="!loadingTableData" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" style="width:0.8rem;height:0.8rem"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" /></svg>
                <svg v-show="loadingTableData" class="loading-spinner-sm" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" style="width:0.8rem;height:0.8rem"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" opacity="0.25"/><path fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                {{ t('admin.storage.reload') }}
              </button>
              <button class="projects-data-btn" @click="handleProjectTableExport">{{ t('admin.storage.export') }}</button>
              <button class="projects-data-btn" @click="showProjectImportModal = true">{{ t('admin.storage.import') }}</button>
              <button v-if="selectedTableDataRowIds.length > 0" class="projects-data-btn projects-data-btn-danger" @click="bulkDeleteProjectRows">{{ t('admin.storage.delete_selected') }} ({{ selectedTableDataRowIds.length }})</button>
              <button class="projects-data-btn projects-data-btn-primary" :disabled="tableDataColumns.length === 0" @click="openCreateProjectRow">{{ t('admin.storage.add_row') }}</button>
              <button class="projects-data-btn" @click="selectedProjectTable = null">{{ t('admin.common.close') }}</button>
            </div>
          </div>
          <div class="projects-search-row">
            <input type="search" v-model="tableDataSearch" class="projects-search" :placeholder="t('admin.storage.search_rows')" />
          </div>
        </div>
        <div v-if="tableDataError" class="projects-alert">{{ tableDataError }}</div>
        <div v-if="tableNotice" class="projects-toast">{{ tableNotice }}</div>
        <div class="projects-table-data-wrap">
          <div v-if="loadingTableData" class="projects-empty">{{ t('admin.storage.loading_rows') }}</div>
          <template v-else>
            <table class="projects-data-grid">
              <thead>
                <tr>
                  <th class="projects-data-check">
                    <input type="checkbox" :checked="allTableDataRowsSelected" @change="toggleAllTableDataRows()" />
                  </th>
                  <th class="sortable" :class="{ 'sorted': tableDataSortBy === 'id' }" @click="toggleTableDataSort('id')">
                    id
                    <span v-if="tableDataSortBy === 'id'" class="sort-arrow">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path :d="tableDataSortArrowPath()" /></svg>
                    </span>
                  </th>
                  <th v-for="column in tableDataColumns" :key="column.name" class="sortable" :class="{ 'sorted': tableDataSortBy === column.name }" :title="column.description || column.data_type" @click="toggleTableDataSort(column.name)">
                    {{ column.name }}
                    <span v-if="tableDataSortBy === column.name" class="sort-arrow">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path :d="tableDataSortArrowPath()" /></svg>
                    </span>
                  </th>
                  <th class="sortable" :class="{ 'sorted': tableDataSortBy === 'created_at' }" @click="toggleTableDataSort('created_at')">
                    {{ t('admin.storage.created') }}
                    <span v-if="tableDataSortBy === 'created_at'" class="sort-arrow">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path :d="tableDataSortArrowPath()" /></svg>
                    </span>
                  </th>
                  <th class="sortable" :class="{ 'sorted': tableDataSortBy === 'updated_at' }" @click="toggleTableDataSort('updated_at')">
                    {{ t('admin.storage.updated') }}
                    <span v-if="tableDataSortBy === 'updated_at'" class="sort-arrow">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path :d="tableDataSortArrowPath()" /></svg>
                    </span>
                  </th>
                  <th class="projects-data-actions">{{ t('admin.common.actions') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in tableDataRows" :key="row.id">
                  <td class="projects-data-check">
                    <input type="checkbox" :checked="selectedTableDataRowIds.includes(row.id)" @change="toggleTableDataRow(row.id)" />
                  </td>
                  <td class="row-id">{{ row.id }}</td>
                  <td v-for="column in tableDataColumns" :key="column.name" :title="displayTableValue(row.data[column.name], column)">
                    {{ displayTableValue(row.data[column.name], column) }}
                  </td>
                  <td>{{ formatTableDate(row.created_at) }}</td>
                  <td>{{ formatTableDate(row.updated_at) }}</td>
                  <td class="projects-data-actions">
                    <button class="projects-action-btn" :title="t('admin.common.edit')" @click="openEditProjectRow(row)">
                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" /></svg>
                    </button>
                    <button class="projects-action-btn projects-action-btn-danger" :title="t('admin.common.delete')" @click="removeProjectRow(row)">
                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-if="tableDataRows.length === 0" class="projects-empty">{{ t('admin.storage.no_rows') }}</div>
          </template>
        </div>
        <div v-if="tableDataTotal > 0" class="projects-pagination">
          <span class="projects-page-total">{{ t('admin.storage.total_rows', { total: tableDataTotal }) }}</span>
          <template v-if="tableDataPages > 1">
            <button class="projects-page-btn" :disabled="tableDataPage <= 1" @click="changeTableDataPage(tableDataPage - 1)">{{ t('admin.storage.prev_page') }}</button>
            <span class="projects-page-info">{{ t('admin.storage.page_x_of_y', { page: tableDataPage, pages: tableDataPages }) }}</span>
            <button class="projects-page-btn" :disabled="tableDataPage >= tableDataPages" @click="changeTableDataPage(tableDataPage + 1)">{{ t('admin.storage.next_page') }}</button>
          </template>
        </div>
      </div>
    </div>

    <!-- â•â•â• COL 4: Chats â•â•â• -->
    <div class="projects-col" :class="{ 'projects-col-hidden': !(selectedProjectId && selectedUserId), 'mobile-pane-hidden': mobilePane !== 'chats' }">
      <div class="projects-panel" v-if="selectedProjectId && selectedUserId">
        <div class="projects-panel-header">
          <div class="projects-panel-title-row">
            <h3 class="projects-panel-title">{{ t('admin.chat.title') }}</h3>
            <button @click="showCreateChatModal = true" class="projects-add-btn">{{ t('admin.chat.new') }}</button>
          </div>
          <div class="projects-search-row">
            <input type="search" v-model="userChatSearch" class="projects-search" :placeholder="t('admin.chat.search')" />
          </div>
        </div>
        <div class="projects-list">
          <template v-if="!loadingChats">
            <div v-for="chat in userChats" :key="chat.id"
              class="chat-card-wrapper"
              :class="{ 'chat-card-selected': selectedChatId === chat.id }"
              @click="selectChat(chat.id)">
              <div class="chat-card-top-row">
                <div class="chat-card-avatar">
                  <svg v-if="!(chatLoading && clickedChatId === chat.id)" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1.25rem;height:1.25rem"><path stroke-linecap="round" stroke-linejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155"/></svg>
                  <svg v-else class="chat-loading-spinner-sm" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" style="width:1.25rem;height:1.25rem"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" opacity="0.25"/><path fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                </div>
                <div class="chat-card-info">
                  <div class="chat-card-name">{{ chat.description || t('admin.chat.no_description') }}</div>
                  
                </div>
                <div class="chat-card-actions">
                  <button @click.stop="editChatDescription(chat.id)" class="chat-card-btn" :title="t('admin.chat.edit')">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" /></svg>
                  </button>
                  <button @click.stop="deleteChat(chat.id)" class="chat-card-btn chat-card-btn-danger" :title="t('admin.chat.delete')">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0
a48.667 48.667 0 0 0-7.5 0" /></svg>
                  </button>
                </div>
              </div>
            </div>
            <!-- An empty chats column used to be one grey line, which read as a
                 blank panel. The card says what is missing and how to fix it. -->
            <div v-if="userChats.length === 0" class="chats-blank">
              <div class="chats-blank-icon">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155"/></svg>
              </div>
              <p class="chats-blank-title">{{ t('admin.chat.no_chats') }}</p>
              <p class="chats-blank-text">{{ t('admin.chat.no_chats_hint') }}</p>
            </div>
          </template>
          <div v-else class="loading-overlay loading-active">
            <div class="loading-spinner"></div>
            <span class="loading-text">{{ t('admin.projects.loading') }}</span>
          </div>
        </div>
      </div>

    </div>

    <!-- --- COL 5: Conversation --- -->
    <div class="projects-col projects-col-chat" :class="{ 'projects-col-hidden': !(selectedProjectId && selectedUserId && selectedChatId), 'mobile-pane-hidden': mobilePane !== 'chat' }">
      <div class="projects-panel chat-panel">
        <template v-if="selectedChatId">
          <div class="projects-panel-header chat-header">
            <div class="projects-panel-title-row" style="justify-content:center">
              <h3 class="projects-panel-title">{{ selectedChat?.description || t('admin.chat.no_description') }}</h3>
            </div>
            <label class="chat-debug-switch" :title="t('admin.chat.debug_mode')">
              <input type="checkbox" v-model="debugMode" />
              <span class="chat-debug-slider"></span>
              <span class="chat-debug-label">{{ t('admin.chat.debug_mode') }}</span>
            </label>
          </div>
          <div
            class="chat-messages"
            ref="messagesRef"
            @click="onMessagesClick"
            @scroll.passive="onMessagesScroll"
          >
            <div v-if="loadingOlderMessages" class="chat-load-older">
              <div class="loading-spinner"></div>
            </div>
            <div v-if="loadingMessages" class="projects-empty">
              <div class="loading-spinner"></div>
            </div>
            <div v-else-if="visibleMessages.length === 0" class="chat-empty">{{ t('admin.chat.no_messages') }}</div>

            <template v-for="(msg, idx) in visibleMessages" :key="msg.id">
              <div class="chat-date-divider" v-if="idx === 0 || new Date(msg.created_at).toDateString() !== new Date(visibleMessages[idx-1].created_at).toDateString()">
                <span>{{ new Date(msg.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }}</span>
              </div>
              <div
                class="chat-msg-row"
                :class="[
                  isOwnMessage(msg) ? 'chat-msg-right' : 'chat-msg-left',
                  { 'chat-msg-grouped': isGroupedWithPrevious(idx) },
                ]"
              >
                <div
                  class="chat-bubble"
                  :class="[
                    isOwnMessage(msg) ? 'chat-bubble-mine' : 'chat-bubble-other',
                    bubbleTone(msg),
                  ]"
                >
                  <div v-if="showSender(idx)" class="chat-bubble-sender">{{ msg.sender_name || msg.sender_type }}</div>
                  <div v-if="debugMode" class="chat-debug-card" :class="{ 'is-open': isDebugExpanded(msg.id) }">
                    <button type="button" class="chat-debug-head" @click="toggleDebugDetails(msg.id)">
                      <span class="chat-debug-headline">
                        <span class="chat-debug-title">
                          <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                          <span>Debug</span>
                          <span class="chat-debug-id-chip">#{{ msg.id }}</span>
                        </span>
                        <span class="chat-debug-badge">{{ msg.message_type }}</span>
                        <svg class="chat-debug-chevron" xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
                      </span>
                      <span class="chat-debug-route">
                        <span class="chat-debug-dot" :class="debugTypeClass(msg.sender_type)"></span>
                        <span class="chat-debug-route-name">{{ msg.sender_name || msg.sender_type || 'null' }}</span>
                        <svg class="chat-debug-route-arrow" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>
                        <span class="chat-debug-dot" :class="debugTypeClass(msg.receiver_type)"></span>
                        <span class="chat-debug-route-name">{{ msg.receiver_name || msg.receiver_type || 'null' }}</span>
                      </span>
                    </button>
                    <div v-if="isDebugExpanded(msg.id)" class="chat-debug-body">
                      <div class="chat-debug-actor" :class="debugTypeClass(msg.sender_type)">
                        <span class="chat-debug-actor-label">Sender</span>
                        <span class="chat-debug-actor-name">{{ msg.sender_name || msg.sender_type || 'null' }}</span>
                        <span class="chat-debug-actor-meta">{{ msg.sender_type || 'null' }} &middot; #{{ msg.sender_id ?? 'null' }}</span>
                      </div>
                      <div class="chat-debug-arrow">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="m6 13 6 6 6-6"/></svg>
                      </div>
                      <div class="chat-debug-actor" :class="debugTypeClass(msg.receiver_type)">
                        <span class="chat-debug-actor-label">Receiver</span>
                        <span class="chat-debug-actor-name">{{ msg.receiver_name || msg.receiver_type || 'null' }}</span>
                        <span class="chat-debug-actor-meta">{{ msg.receiver_type || 'null' }} &middot; #{{ msg.receiver_id ?? 'null' }}</span>
                      </div>
                    </div>
                  </div>
                  <div class="chat-bubble-text markdown-content" v-html="renderMarkdown(msg.content, { copyLabel: t('admin.chat.copy_table') })"></div>
                  <span class="chat-bubble-time">{{ new Date(msg.created_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) }}</span>
                </div>
              </div>
            </template>
            <div v-if="typingUser" class="chat-typing-indicator">
              <span class="chat-typing-dots"><span></span><span></span><span></span></span>
              <span class="chat-typing-text">{{ t('admin.chat.typing', { name: typingUser }) }}</span>
            </div>
          </div>
          <div class="chat-input-area">
            <textarea
              v-model="newMessageContent"
              :placeholder="t('admin.chat.type_message')"
              class="chat-input"
              :readonly="agentLoopRunning"
              @keydown.enter.exact.prevent="sendMessageAction"
              rows="2"
            ></textarea>
            <button
              class="chat-send-btn"
              :class="{ 'chat-stop-btn': agentLoopRunning }"
              @click="agentLoopRunning ? stopAgentLoop() : sendMessageAction()"
              :disabled="agentLoopStopping || (!agentLoopRunning && (sending || !newMessageContent.trim()))"
            >
              {{ agentLoopRunning ? (agentLoopStopping ? 'Stopping...' : 'Stop') : t('admin.chat.send') }}
            </button>
          </div>
        </template>
        <template v-else-if="selectedUserId && !selectedChatId">
          <div class="chat-empty">{{ t('admin.chat.no_messages') }}</div>
        </template>
      </div>
    </div>

    <!-- ---- MODALS ---- -->

    <!-- Project Create/Edit Modal -->
    <div v-if="showProjectModal" class="projects-overlay" @click.self="showProjectModal = false">
      <div class="projects-modal">
        <div class="projects-modal-header">
          <h3>{{ editingId ? t('admin.projects.edit') : t('admin.projects.create') }}</h3>
          <button @click="showProjectModal = false" class="projects-modal-close">&times;</button>
        </div>
        <div class="projects-modal-body">
          <label class="projects-field">
            <span>{{ t('admin.projects.form_name') }}</span>
            <input type="text" v-model="projectForm.name" class="projects-input" required />
          </label>
          <label class="projects-field">
            <span>{{ t('admin.projects.form_description') }}</span>
            <textarea v-model="projectForm.description" class="projects-input" rows="3"></textarea>
          </label>
          <label class="projects-field projects-field-checkbox">
            <input type="checkbox" v-model="projectForm.is_active" class="projects-checkbox" />
            <span>{{ t('admin.projects.form_active') }}</span>
          </label>
        </div>
        <div class="projects-modal-footer">
          <button @click="showProjectModal = false" class="projects-btn projects-btn-cancel">{{ t('admin.projects.cancel') }}</button>
          <button @click="saveProject" class="projects-btn projects-btn-save">{{ t('admin.projects.save') }}</button>
        </div>
      </div>
    </div>

    <!-- Create Agent Modal -->
    <div v-if="showCreateAgentModal" class="projects-overlay" @click.self="showCreateAgentModal = false">
      <div class="projects-modal projects-agent-modal">
        <div class="projects-modal-header">
          <h3>{{ t('admin.agents.create_title') }}</h3>
          <button @click="showCreateAgentModal = false" class="projects-modal-close">&times;</button>
        </div>
        <div class="projects-modal-body">
          <label class="projects-field">
            <span>{{ t('admin.agents.create_name') }}</span>
            <input type="text" v-model="createAgentName" class="projects-input" required />
          </label>
          <label class="projects-field">
            <span>{{ t('admin.agents.create_desc') }}</span>
            <textarea v-model="createAgentDescription" class="projects-input" rows="3"></textarea>
          </label>
          <div class="projects-field">
            <span>{{ t('admin.agents.skills') }}</span>
            <div class="projects-skill-picker">
              <label v-if="activeSkills.length === 0" class="projects-skill-option projects-skill-empty">
                {{ t('admin.agents.no_active_skills') }}
              </label>
              <label v-for="skill in activeSkills" :key="skill.id" class="projects-skill-option">
                <input
                  type="checkbox"
                  class="projects-checkbox"
                  :checked="createAgentSkillIds.includes(skill.id)"
                  @change="toggleCreateAgentSkill(skill.id, ($event.target as HTMLInputElement).checked)"
                />
                <span class="projects-skill-main">
                  <span>{{ skill.name }}</span>
                  <small>{{ skill.description || t('admin.common.no_description') }}</small>
                </span>
              </label>
            </div>
          </div>
          <div class="projects-field">
            <span>{{ t('admin.agents.context_tools') }}</span>
            <small class="projects-field-hint">{{ t('admin.agents.context_tools_hint') }}</small>
            <p v-if="createAgentContextTools.length === 0" class="projects-context-empty">
              {{ t('admin.agents.context_tools_empty') }}
            </p>
            <div v-for="(entry, index) in createAgentContextTools" :key="entry.tool_id" class="projects-context-row">
              <div class="projects-context-head">
                <span class="projects-context-name">{{ entry.name }}</span>
                <span v-if="!contextToolIsActive(entry)" class="projects-context-inactive">{{ t('admin.agents.context_inactive') }}</span>
                <button type="button" class="projects-context-remove" @click="createAgentContextTools = removeContextToolEntry(createAgentContextTools, index)">&times;</button>
              </div>
              <input
                class="projects-input"
                :value="entry.comment"
                :placeholder="t('admin.agents.context_comment_placeholder')"
                @input="createAgentContextTools = patchContextToolEntry(createAgentContextTools, index, { comment: ($event.target as HTMLInputElement).value })"
              />
              <input
                class="projects-input projects-context-args"
                :value="entry.arguments"
                :placeholder="t('admin.agents.context_arguments_placeholder')"
                @input="createAgentContextTools = patchContextToolEntry(createAgentContextTools, index, { arguments: ($event.target as HTMLInputElement).value })"
              />
            </div>
            <div class="projects-context-add">
              <select
                class="projects-input"
                :value="createContextToolToAdd ?? ''"
                @change="createContextToolToAdd = ($event.target as HTMLSelectElement).value === '' ? null : Number(($event.target as HTMLSelectElement).value)"
              >
                <option value="">{{ t('admin.agents.context_add_placeholder') }}</option>
                <option v-for="tool in contextToolOptions(createAgentSkillIds, createAgentContextTools)" :key="tool.id" :value="tool.id">{{ tool.name }}</option>
              </select>
              <button
                type="button"
                class="projects-btn projects-btn-cancel"
                :disabled="createContextToolToAdd === null"
                @click="createAgentContextTools = addContextToolEntry(createAgentContextTools, createContextToolToAdd, contextToolOptions(createAgentSkillIds, createAgentContextTools)); createContextToolToAdd = null"
              >+</button>
            </div>
          </div>
          <label class="projects-field">
            <span>{{ t('admin.agents.generate_from_description') }}</span>
            <textarea
              v-model="createAgentGeneratorPrompt"
              class="projects-input projects-generator-input"
              rows="4"
              :placeholder="t('admin.agents.generate_placeholder')"
            ></textarea>
          </label>
        </div>
        <div class="projects-modal-footer">
          <button @click="generateCreateAgentFields" class="projects-btn projects-btn-cancel generate-btn" :disabled="generatingAgent">
            <span v-if="generatingAgent" class="generate-spinner"></span>
            <span>{{ generatingAgent ? t('admin.common.generating') : t('admin.common.generate') }}</span>
          </button>
          <button @click="showCreateAgentModal = false" class="projects-btn projects-btn-cancel">{{ t('admin.projects.cancel') }}</button>
          <button @click="createAgentAction" class="projects-btn projects-btn-save">{{ t('admin.agents.create_btn') }}</button>
        </div>
      </div>
    </div>

    <!-- Create Chat Modal -->
    <div v-if="showCreateChatModal" class="projects-overlay" @click.self="showCreateChatModal = false">
      <div class="projects-modal projects-agent-modal">
        <div class="projects-modal-header">
          <h3>{{ t('admin.chat.create_title') }}</h3>
          <button @click="showCreateChatModal = false" class="projects-modal-close">&times;</button>
        </div>
        <div class="projects-modal-body">
          <label class="projects-field">
            <span>{{ t('admin.chat.create_description') }}</span>
            <input type="text" v-model="createChatDescription" class="projects-input" required />
          </label>
        </div>
        <div class="projects-modal-footer">
          <button @click="showCreateChatModal = false" class="projects-btn projects-btn-cancel">{{ t('admin.projects.cancel') }}</button>
          <button @click="createChatAction" class="projects-btn projects-btn-save">{{ t('admin.chat.create_btn') }}</button>
        </div>
      </div>
    </div>

    <!-- Agent Edit Modal -->
    <div v-if="showAgentEditModal" class="projects-overlay" @click.self="showAgentEditModal = false">
      <div class="projects-modal" style="max-width:480px">
        <div class="projects-modal-header">
          <h3>{{ t('admin.agents.edit_title') }}</h3>
          <button @click="showAgentEditModal = false" class="projects-modal-close">&times;</button>
        </div>
        <div class="projects-modal-body">
          <label class="projects-field">
            <span>{{ t('admin.agents.create_name') }}</span>
            <input type="text" v-model="editAgentName" class="projects-input" required />
          </label>
          <label class="projects-field">
            <span>{{ t('admin.agents.create_desc') }}</span>
            <textarea v-model="editAgentDescription" class="projects-input" rows="3"></textarea>
          </label>
          <div class="projects-field">
            <span>{{ t('admin.agents.skills') }}</span>
            <div class="projects-skill-picker">
              <label v-if="activeSkills.length === 0" class="projects-skill-option projects-skill-empty">
                {{ t('admin.agents.no_active_skills') }}
              </label>
              <label v-for="skill in activeSkills" :key="skill.id" class="projects-skill-option">
                <input
                  type="checkbox"
                  class="projects-checkbox"
                  :checked="editAgentSkillIds.includes(skill.id)"
                  @change="toggleEditAgentSkill(skill.id, ($event.target as HTMLInputElement).checked)"
                />
                <span class="projects-skill-main">
                  <span>{{ skill.name }}</span>
                  <small>{{ skill.description || t('admin.common.no_description') }}</small>
                </span>
              </label>
            </div>
          </div>
          <div class="projects-field">
            <span>{{ t('admin.agents.context_tools') }}</span>
            <small class="projects-field-hint">{{ t('admin.agents.context_tools_hint') }}</small>
            <p v-if="editAgentContextTools.length === 0" class="projects-context-empty">
              {{ t('admin.agents.context_tools_empty') }}
            </p>
            <div v-for="(entry, index) in editAgentContextTools" :key="entry.tool_id" class="projects-context-row">
              <div class="projects-context-head">
                <span class="projects-context-name">{{ entry.name }}</span>
                <span v-if="!contextToolIsActive(entry)" class="projects-context-inactive">{{ t('admin.agents.context_inactive') }}</span>
                <button type="button" class="projects-context-remove" @click="editAgentContextTools = removeContextToolEntry(editAgentContextTools, index)">&times;</button>
              </div>
              <input
                class="projects-input"
                :value="entry.comment"
                :placeholder="t('admin.agents.context_comment_placeholder')"
                @input="editAgentContextTools = patchContextToolEntry(editAgentContextTools, index, { comment: ($event.target as HTMLInputElement).value })"
              />
              <input
                class="projects-input projects-context-args"
                :value="entry.arguments"
                :placeholder="t('admin.agents.context_arguments_placeholder')"
                @input="editAgentContextTools = patchContextToolEntry(editAgentContextTools, index, { arguments: ($event.target as HTMLInputElement).value })"
              />
            </div>
            <div class="projects-context-add">
              <select
                class="projects-input"
                :value="editContextToolToAdd ?? ''"
                @change="editContextToolToAdd = ($event.target as HTMLSelectElement).value === '' ? null : Number(($event.target as HTMLSelectElement).value)"
              >
                <option value="">{{ t('admin.agents.context_add_placeholder') }}</option>
                <option v-for="tool in contextToolOptions(editAgentSkillIds, editAgentContextTools)" :key="tool.id" :value="tool.id">{{ tool.name }}</option>
              </select>
              <button
                type="button"
                class="projects-btn projects-btn-cancel"
                :disabled="editContextToolToAdd === null"
                @click="editAgentContextTools = addContextToolEntry(editAgentContextTools, editContextToolToAdd, contextToolOptions(editAgentSkillIds, editAgentContextTools)); editContextToolToAdd = null"
              >+</button>
            </div>
          </div>
          <label class="projects-field">
            <span>{{ t('admin.agents.generate_from_description') }}</span>
            <textarea
              v-model="editAgentGeneratorPrompt"
              class="projects-input projects-generator-input"
              rows="4"
              :placeholder="t('admin.agents.generate_placeholder')"
            ></textarea>
          </label>
          <label class="projects-field projects-field-checkbox">
            <input type="checkbox" v-model="editAgentIsActive" class="projects-checkbox" />
            <span>{{ t('admin.projects.form_active') }}</span>
          </label>
        </div>
        <div class="projects-modal-footer">
          <button @click="generateEditAgentFields" class="projects-btn projects-btn-cancel generate-btn" :disabled="generatingAgent">
            <span v-if="generatingAgent" class="generate-spinner"></span>
            <span>{{ generatingAgent ? t('admin.common.generating') : t('admin.common.generate') }}</span>
          </button>
          <button @click="showAgentEditModal = false" class="projects-btn projects-btn-cancel">{{ t('admin.projects.cancel') }}</button>
          <button @click="updateAgent" class="projects-btn projects-btn-save">{{ t('admin.projects.save') }}</button>
        </div>
      </div>
    </div>

    <!-- Edit Chat Modal -->
    <div v-if="showChatModal" class="projects-overlay" @click.self="showChatModal = false">
      <div class="projects-modal" style="max-width:480px">
        <div class="projects-modal-header">
          <h3>{{ t('admin.chat.edit') }}</h3>
          <button @click="showChatModal = false" class="projects-modal-close">&times;</button>
        </div>
        <div class="projects-modal-body">
          <label class="projects-field">
            <span>{{ t('admin.chat.edit_description') }}</span>
            <input type="text" v-model="chatForm.description" class="projects-input" required />
          </label>
        </div>
        <div class="projects-modal-footer">
          <button @click="showChatModal = false" class="projects-btn projects-btn-cancel">{{ t('admin.projects.cancel') }}</button>
          <button @click="updateChatDescription" class="projects-btn projects-btn-save">{{ t('admin.projects.save') }}</button>
        </div>
      </div>
    </div>

    <!-- Assign Agent Modal -->
    <div v-if="showAddAgentModal" class="projects-overlay" @click.self="showAddAgentModal = false">
      <div class="projects-modal">
        <div class="projects-modal-header">
          <h3>{{ t('admin.agents.title') }}</h3>
          <button @click="showAddAgentModal = false" class="projects-modal-close">&times;</button>
        </div>
        <div class="projects-modal-body">
          <input type="search" v-model="memberSearch" class="projects-search" :placeholder="t('admin.assign_member.search')" />
          <div class="projects-list" style="max-height:15rem;min-height:auto;padding:0.5rem 0">
            <div v-if="loadingAvailable" class="projects-empty">{{ t('admin.projects.loading') }}</div>
            <div v-else-if="availableMembers.length === 0" class="projects-empty">{{ t('admin.assign_member.no_available') }}</div>
            <div v-for="m in availableMembers" :key="m.id ?? m.name" class="projects-item-wrapper" @click="assignMember(m, 'agent')" style="cursor:pointer">
              <div class="projects-item-content">
                <div class="projects-item-name">{{ m.name }}</div>
                <div v-if="m.description" class="projects-item-meta">{{ m.description }}</div>
              </div>
            </div>
          </div>
          <div v-if="memberTotal > 0" class="projects-pagination">
            <span class="projects-page-total">{{ t('admin.storage.total_rows', { total: memberTotal }) }}</span>
            <template v-if="memberPages > 1">
              <button class="projects-page-btn" :disabled="memberPage <= 1" @click="changeMemberPage(memberPage - 1)">{{ t('admin.storage.prev_page') }}</button>
              <span class="projects-page-info">{{ t('admin.storage.page_x_of_y', { page: memberPage, pages: memberPages }) }}</span>
              <button class="projects-page-btn" :disabled="memberPage >= memberPages" @click="changeMemberPage(memberPage + 1)">{{ t('admin.storage.next_page') }}</button>
            </template>
          </div>
        </div>
        <div class="projects-modal-footer">
          <button @click="showAddAgentModal = false" class="projects-btn projects-btn-cancel">{{ t('admin.assign_member.close') }}</button>
        </div>
      </div>
    </div>

    <!-- Assign User Modal -->
    <div v-if="showAddUserModal" class="projects-overlay" @click.self="showAddUserModal = false">
      <div class="projects-modal">
        <div class="projects-modal-header">
          <h3>{{ t('admin.sidebar.users') }}</h3>
          <button @click="showAddUserModal = false" class="projects-modal-close">&times;</button>
        </div>
        <div class="projects-modal-body">
          <input type="search" v-model="memberSearch" class="projects-search" :placeholder="t('admin.assign_member.search')" />
          <div class="projects-list" style="max-height:15rem;min-height:auto;padding:0.5rem 0">
            <div v-if="loadingAvailable" class="projects-empty">{{ t('admin.projects.loading') }}</div>
            <div v-else-if="availableMembers.length === 0" class="projects-empty">{{ t('admin.assign_member.no_available') }}</div>
            <div v-for="m in availableMembers" :key="m.id" class="projects-item-wrapper" @click="assignMember(m, 'user')" style="cursor:pointer">
              <div class="projects-item-content">
                <div class="projects-item-name">{{ m.name }}</div>
                <div v-if="m.email" class="projects-item-meta">{{ m.email }}</div>
              </div>
            </div>
          </div>
          <div v-if="memberTotal > 0" class="projects-pagination">
            <span class="projects-page-total">{{ t('admin.storage.total_rows', { total: memberTotal }) }}</span>
            <template v-if="memberPages > 1">
              <button class="projects-page-btn" :disabled="memberPage <= 1" @click="changeMemberPage(memberPage - 1)">{{ t('admin.storage.prev_page') }}</button>
              <span class="projects-page-info">{{ t('admin.storage.page_x_of_y', { page: memberPage, pages: memberPages }) }}</span>
              <button class="projects-page-btn" :disabled="memberPage >= memberPages" @click="changeMemberPage(memberPage + 1)">{{ t('admin.storage.next_page') }}</button>
            </template>
          </div>
        </div>
        <div class="projects-modal-footer">
          <button @click="showAddUserModal = false" class="projects-btn projects-btn-cancel">{{ t('admin.assign_member.close') }}</button>
        </div>
      </div>
    </div>

    <!-- Assign Table Modal -->
    <div v-if="showAddTableModal" class="projects-overlay" @click.self="showAddTableModal = false">
      <div class="projects-modal">
        <div class="projects-modal-header">
          <h3>{{ t('admin.storage.tables') }}</h3>
          <button @click="showAddTableModal = false" class="projects-modal-close">&times;</button>
        </div>
        <div class="projects-modal-body">
          <input type="search" v-model="memberSearch" class="projects-search" :placeholder="t('admin.assign_member.search')" />
          <div class="projects-list" style="max-height:15rem;min-height:auto;padding:0.5rem 0">
            <div v-if="loadingAvailable" class="projects-empty">{{ t('admin.projects.loading') }}</div>
            <div v-else-if="availableMembers.length === 0" class="projects-empty">{{ t('admin.assign_member.no_available') }}</div>
            <div v-for="m in availableMembers" :key="m.name" class="projects-item-wrapper" @click="assignMember(m, 'table')" style="cursor:pointer">
              <div class="projects-item-content">
                <div class="projects-item-name">{{ m.name }}</div>
                <div class="projects-item-meta">{{ m.columns.length }} {{ t('admin.storage.columns').toLowerCase() }} &middot; {{ t('admin.storage.total_rows', { total: m.row_count }) }}</div>
              </div>
            </div>
          </div>
          <div v-if="memberTotal > 0" class="projects-pagination">
            <span class="projects-page-total">{{ t('admin.storage.total_rows', { total: memberTotal }) }}</span>
            <template v-if="memberPages > 1">
              <button class="projects-page-btn" :disabled="memberPage <= 1" @click="changeMemberPage(memberPage - 1)">{{ t('admin.storage.prev_page') }}</button>
              <span class="projects-page-info">{{ t('admin.storage.page_x_of_y', { page: memberPage, pages: memberPages }) }}</span>
              <button class="projects-page-btn" :disabled="memberPage >= memberPages" @click="changeMemberPage(memberPage + 1)">{{ t('admin.storage.next_page') }}</button>
            </template>
          </div>
        </div>
        <div class="projects-modal-footer">
          <button @click="showAddTableModal = false" class="projects-btn projects-btn-cancel">{{ t('admin.assign_member.close') }}</button>
        </div>
      </div>
    </div>

    <!-- Row edit/create modal (table data) -->
    <div v-if="showProjectRowModal" class="projects-overlay" @click.self="showProjectRowModal = false">
      <div class="projects-modal">
        <div class="projects-modal-header">
          <h3>{{ editingProjectRowId ? t('admin.storage.edit_row') : t('admin.storage.create_row') }}</h3>
          <button @click="showProjectRowModal = false" class="projects-modal-close">&times;</button>
        </div>
        <div class="projects-modal-body">
          <div v-if="projectRowError" class="projects-alert">{{ projectRowError }}</div>
          <label v-for="column in tableDataColumns" :key="column.name" class="projects-field">
            <span>{{ column.name }} <small style="color:#9ca3af;font-weight:400">{{ column.data_type }}</small></span>
            <textarea
              v-if="['longtext', 'json'].includes(tableColumnKind(column))"
              v-model="projectRowData[column.name]"
              class="projects-input projects-textarea"
            />
            <select v-else-if="tableColumnKind(column) === 'boolean'" v-model="projectRowData[column.name]" class="projects-input">
              <option value="">-</option>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
            <input
              v-else-if="tableColumnKind(column) === 'datetime'"
              v-model="projectRowData[column.name]"
              class="projects-input"
              type="datetime-local"
            />
            <input v-else-if="tableColumnKind(column) === 'date'" v-model="projectRowData[column.name]" class="projects-input" type="date" />
            <input v-else-if="tableColumnKind(column) === 'time'" v-model="projectRowData[column.name]" class="projects-input" type="time" />
            <input
              v-else-if="tableColumnKind(column) === 'number'"
              v-model="projectRowData[column.name]"
              class="projects-input"
              type="number"
              step="any"
            />
            <input v-else v-model="projectRowData[column.name]" class="projects-input" type="text" />
          </label>
        </div>
        <div class="projects-modal-footer">
          <button @click="showProjectRowModal = false" class="projects-btn projects-btn-cancel">{{ t('admin.common.cancel') }}</button>
          <button class="projects-btn projects-btn-save" :disabled="projectRowSaving" @click="saveProjectRow">
            {{ projectRowSaving ? t('admin.common.saving') : t('admin.storage.save_row') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Import Excel modal (table data) -->
    <div v-if="showProjectImportModal" class="projects-overlay" @click.self="closeProjectImportModal">
      <div class="projects-modal projects-modal-lg">
        <div class="projects-modal-header">
          <h3>{{ t('admin.storage.import_excel') }}</h3>
          <button @click="closeProjectImportModal" class="projects-modal-close">&times;</button>
        </div>
        <div class="projects-modal-body">
          <p class="projects-help">{{ t('admin.storage.upload_help') }}</p>
          <input class="projects-input" type="file" accept=".xlsx" @change="onProjectExcelFileChange" />
          <p v-if="excelFile" class="projects-file-name">{{ excelFile.name }}</p>
          <div v-if="previewingExcel" class="projects-empty">{{ t('admin.storage.reading_workbook') }}</div>
          <div v-else-if="excelPreview" class="projects-mapping-panel">
            <div class="projects-mapping-header">
              <span>{{ t('admin.storage.database_column') }}</span>
              <span>{{ t('admin.storage.excel_column') }}</span>
            </div>
            <div v-for="column in tableDataColumns" :key="column.name" class="projects-mapping-row">
              <div class="projects-mapping-db-col">
                <strong>{{ column.name }}</strong>
                <span>{{ column.data_type }}</span>
              </div>
              <div class="projects-mapping-select-wrap">
                <select v-model="importMapping[column.name]" class="projects-input">
                  <option value="">{{ t('admin.storage.do_not_import') }}</option>
                  <option v-for="header in excelPreview.headers" :key="header" :value="header">{{ header }}</option>
                </select>
                <span v-if="importMapping[column.name]" class="projects-mapping-sample">
                  {{ t('admin.storage.sample', { value: projectSampleForHeader(importMapping[column.name]) || '-' }) }}
                </span>
              </div>
            </div>
          </div>
        </div>
        <div class="projects-modal-footer">
          <button @click="closeProjectImportModal" class="projects-btn projects-btn-cancel">{{ t('admin.common.cancel') }}</button>
          <button class="projects-btn projects-btn-save" :disabled="importing || !excelFile || !excelPreview" @click="handleProjectImport">
            {{ importing ? t('admin.storage.importing') : t('admin.storage.import') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Edit table modal (like /admin/storage) -->
    <div v-if="showProjectTableModal" class="projects-overlay" @click.self="showProjectTableModal = false">
      <div class="projects-modal projects-modal-lg">
        <div class="projects-modal-header">
          <h3>{{ editingProjectTableName ? t('admin.storage.edit_table') : t('admin.storage.create_table') }}</h3>
          <button @click="showProjectTableModal = false" class="projects-modal-close">&times;</button>
        </div>
        <div class="projects-modal-body">
          <div v-if="projectTableError" class="projects-alert">{{ projectTableError }}</div>
          <label class="projects-field">
            <span>{{ t('admin.common.name') }}</span>
            <input v-model="projectTableName" class="projects-input" type="text" placeholder="my_custom_data" />
          </label>
          <label class="projects-field">
            <span>{{ t('admin.common.description') }}</span>
            <input v-model="projectTableDescription" class="projects-input" type="text" :placeholder="t('admin.storage.optional_description')" />
          </label>

          <div class="projects-column-header">
            <strong>{{ t('admin.storage.columns') }}</strong>
            <button class="projects-add-btn" @click="addProjectColumn">{{ t('admin.storage.add_column') }}</button>
          </div>

          <div v-if="projectModalColumns.length === 0" class="projects-empty" style="padding:0.75rem 0">{{ t('admin.storage.no_columns') }}</div>
          <div v-for="(column, index) in projectModalColumns" :key="index" class="projects-column-row">
            <input v-model="column.name" class="projects-input" type="text" placeholder="column_name" />
            <input v-model="column.description" class="projects-input" type="text" :placeholder="t('admin.common.description')" />
            <select v-model="column.data_type" class="projects-input type-select">
              <option v-for="type in dataTypes" :key="type" :value="type">{{ type }}</option>
            </select>
            <input v-if="column.data_type === 'string'" v-model.number="column.length" class="projects-input length-input" type="number" min="1" :placeholder="t('admin.storage.length')" />
            <label class="projects-field-checkbox nullable-check">
              <input v-model="column.nullable" type="checkbox" class="projects-checkbox" />
              {{ t('admin.storage.nullable') }}
            </label>
            <input v-model="column.default_value" class="projects-input default-input" type="text" :placeholder="t('admin.storage.default')" />
            <button class="projects-action-btn projects-action-btn-danger" :title="t('admin.storage.remove')" @click="removeProjectColumn(index)">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>
            </button>
          </div>
        </div>
        <div class="projects-modal-footer">
          <button @click="showProjectTableModal = false" class="projects-btn projects-btn-cancel">{{ t('admin.common.cancel') }}</button>
          <button class="projects-btn projects-btn-save" :disabled="projectTableSaving" @click="saveProjectTable">
            {{ projectTableSaving ? t('admin.common.saving') : t('admin.storage.save_table') }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>
<style scoped>
@keyframes spin { to { transform: rotate(360deg); } }

.loading-overlay {
  position: absolute; inset: 0;
  display: none; flex-direction: column;
  align-items: center; justify-content: center; gap: 0.5rem;
  background: rgba(255,255,255,0.85);
  z-index: 10;
}
.loading-overlay.loading-active { display: flex; }
.loading-spinner {
  width: 1.5rem; height: 1.5rem;
  border: 2px solid #e5e7eb;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
.loading-text { font-size: 0.875rem; color: #9ca3af; }

.projects-layout {
  display: grid;
  /* The conversation is the only column rendering prose and tables, so it takes
     the larger share of the free width instead of an even split. */
  grid-template-columns: 11rem 12.5rem minmax(0, 1fr) 11rem minmax(0, 1.75fr);
  gap: 1rem;
  align-items: stretch;
  width: 100%;
  min-width: 1200px;
  overflow-x: auto;
  padding: 1rem;
  height: var(--shell-content-height);
}
.projects-col { min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.projects-col-hidden { display: none !important; }
.projects-panel {
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  background: #fff;
  display: flex; flex-direction: column;
  overflow: hidden;
  flex: 1;
  min-height: 0;
}
.projects-panel-header {
  padding: 0.75rem;
  border-bottom: 1px solid #e5e7eb;
  display: flex; flex-direction: column; gap: 0.5rem;
}
.projects-panel-title-row {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 0.375rem;
}
.projects-panel-title {
  margin: 0; font-size: 0.875rem; font-weight: 600;
  color: #374151;
}
.projects-search-row { width: 100%; }
.projects-add-btn {
  font-size: 0.75rem; font-weight: 600;
  padding: 0.25rem 0.625rem;
  border-radius: 0.375rem;
  border: 1px solid #a5b4fc;
  background: #eef2ff;
  color: #4f46e5;
  cursor: pointer; transition: all 0.1s;
  white-space: nowrap;
}
.projects-add-btn:hover { background: #e0e7ff; }
.projects-search {
  width: 100%; padding: 0.375rem 0.625rem;
  border: 1px solid #d1d5db;
  border-radius: 0.5rem; font-size: 0.8125rem;
  outline: none; box-sizing: border-box;
  background: #fff;
  color: #111827;
}
.projects-search:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 2px #c7d2fe;
}
.projects-list {
  flex: 1; overflow-y: auto; padding: 0.5rem;
  display: flex; flex-direction: column; gap: 0.25rem;
  min-height: 6rem; position: relative;
}
.projects-item-wrapper {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.5rem 0.625rem;
  border: 1px solid transparent;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.1s ease;
}
.projects-item-wrapper:hover { background: #f9fafb; }
.projects-item-selected {
  background: #eef2ff;
  border-color: #a5b4fc;
}
.projects-item-content { flex: 1; min-width: 0; }
.projects-item-name {
  font-size: 0.8125rem; font-weight: 500;
  color: #111827;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.projects-item-meta { margin-top: 0.125rem; }
.projects-item-desc {
  font-size: 0.75rem; color: #6b7280;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
  line-height: 1.4;
}
.projects-item-actions {
  display: flex; align-items: center; gap: 0.125rem;
  flex-shrink: 0;
}
.projects-action-btn {
  width: 1.5rem; height: 1.5rem;
  display: flex; align-items: center; justify-content: center;
  padding: 0; border: none; background: transparent;
  color: #9ca3af; cursor: pointer;
  border-radius: 0.25rem;
}
.projects-action-btn:hover { color: #4f46e5; background: #eef2ff; }
.projects-action-btn-danger:hover { color: #dc2626; background: #fef2f2; }
.projects-item-name .projects-system-badge {
  margin-left: 0.4rem; vertical-align: middle;
}
.projects-system-badge {
  display: inline-flex; align-items: center; gap: 0.25rem;
  margin-top: 0.25rem;
  font-size: 0.68rem; font-weight: 600;
  color: #b45309;
  background: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 999px;
  padding: 0.1rem 0.45rem;
  width: fit-content;
}
.projects-project-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-top: 0.3rem;
}
.projects-project-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: #4f46e5;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  border-radius: 999px;
  padding: 0.08rem 0.5rem;
}
.projects-column-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 0.25rem;
}
.projects-column-row {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.45rem 0;
  border-bottom: 1px solid #f1f5f9;
}
.projects-column-row .projects-input { min-width: 0; }
.projects-column-row .type-select { max-width: 9rem; }
.projects-column-row .length-input { max-width: 5rem; }
.projects-column-row .default-input { max-width: 7rem; }
.projects-column-row .nullable-check {
  display: flex; align-items: center; gap: 0.25rem;
  color: #475569; font-size: 0.76rem; white-space: nowrap;
}
.projects-empty {
  padding: 2rem 1rem; text-align: center;
  font-size: 0.875rem; color: #9ca3af;
}
/* The chats panel with nothing in it: a card rather than a bare grey line, so
   the column reads as "nothing here yet" instead of "still loading". */
.chats-blank {
  margin: 1rem 0.5rem;
  padding: 1.25rem 0.75rem;
  text-align: center;
  border: 1px dashed #e5e7eb;
  border-radius: 0.75rem;
  background: #fbfbfe;
}
.chats-blank-icon {
  width: 2.5rem; height: 2.5rem;
  margin: 0 auto 0.75rem;
  display: flex; align-items: center; justify-content: center;
  border-radius: 0.75rem;
  background: #eef2ff; color: #4f46e5;
}
.chats-blank-icon svg { width: 1.375rem; height: 1.375rem; }
.chats-blank-title {
  margin: 0 0 0.375rem;
  font-size: 0.875rem; font-weight: 600; color: #374151;
}
.chats-blank-text {
  margin: 0;
  font-size: 0.8125rem; line-height: 1.5; color: #6b7280;
}
.projects-pagination {
  display: flex; align-items: center; justify-content: flex-end;
  gap: 0.5rem; padding: 0.5rem 0.75rem;
  border-top: 1px solid #e5e7eb; flex-shrink: 0;
}
.projects-page-total {
  font-size: 0.75rem; color: #94a3b8;
  margin-right: auto; white-space: nowrap;
}
.projects-page-info {
  font-size: 0.78rem; color: #64748b; white-space: nowrap;
}
.projects-page-btn {
  font-size: 0.72rem; font-weight: 600;
  padding: 0.22rem 0.55rem;
  border-radius: 0.375rem;
  border: 1px solid #d1d5db;
  background: #fff; color: #374151;
  cursor: pointer; transition: all 0.1s;
  white-space: nowrap;
}
.projects-page-btn:hover:not(:disabled) { background: #f3f4f6; border-color: #9ca3af; }
.projects-page-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* Chat styles */
.projects-col-chat { min-width: 0; height: 100%; display: flex; }
.projects-col-flow { min-width: 0; height: 100%; display: flex; flex-direction: column; gap: 0.5rem; overflow: hidden; }
.chat-panel { display: flex; flex-direction: column; width: 100%; flex: 1; min-height: 0; }
.chat-header { flex-shrink: 0; }
.chat-debug-switch {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  cursor: pointer;
  user-select: none;
  padding: 0.15rem 0;
}
.chat-debug-switch input[type="checkbox"] {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.chat-debug-slider {
  position: relative;
  width: 1.9rem;
  height: 1.05rem;
  border-radius: 999px;
  background: #cbd5e1;
  transition: background 0.15s;
  flex-shrink: 0;
}
.chat-debug-slider::after {
  content: "";
  position: absolute;
  top: 0.13rem;
  left: 0.13rem;
  width: 0.79rem;
  height: 0.79rem;
  border-radius: 999px;
  background: #fff;
  transition: transform 0.15s;
}
.chat-debug-switch input:checked + .chat-debug-slider {
  background: #6366f1;
}
.chat-debug-switch input:checked + .chat-debug-slider::after {
  transform: translateX(0.85rem);
}
.chat-debug-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: #64748b;
}
.chat-messages {
  flex: 1 1 auto; overflow-y: auto; padding: 1rem 0.875rem 1.25rem;
  display: flex; flex-direction: column; gap: 0.625rem;
  min-height: 0;
  /* Soft wash so the white cards and indigo bubbles sit on a surface. */
  background: linear-gradient(180deg, #f8fafc 0%, #f3f5fb 100%);
}
/* Sits above the first bubble while an older page is on its way in. */
.chat-load-older { display: flex; justify-content: center; padding: 0.25rem 0 0.5rem; }
.chat-load-older .loading-spinner { width: 1rem; height: 1rem; }
.chat-date-divider { display: flex; justify-content: center; align-items: center; padding: 0.25rem 0 0.5rem; }
.chat-date-divider span {
  font-size: 0.6875rem; font-weight: 600; color: #6b7280;
  background: #eef2f7;
  padding: 0.15rem 0.6rem; border-radius: 9999px;
}
.chat-msg-row { display: flex; animation: chat-fade-up 0.22s ease-out; }
/* A follow-up bubble from the same sender sits closer to the one above it. */
.chat-msg-row.chat-msg-grouped { margin-top: -0.35rem; }
@keyframes chat-fade-up { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
.chat-msg-left { justify-content: flex-start; }
.chat-msg-right { justify-content: flex-end; }
.chat-bubble {
  max-width: 88%;
  padding: 0.6rem 0.8rem 0.45rem;
  border-radius: 0.9rem;
  font-size: 0.85rem;
  line-height: 1.6;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
}
.chat-bubble-mine {
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  color: #fff;
  border-bottom-right-radius: 0.3rem;
  box-shadow: 0 4px 14px -5px rgba(79, 70, 229, 0.5);
}
.chat-bubble-other {
  background: #fff;
  color: #1f2937;
  border: 1px solid #e6eaf3;
  border-bottom-left-radius: 0.3rem;
  box-shadow: 0 3px 12px -7px rgba(15, 23, 42, 0.3);
}
/* Direction tints. The surface says who is talking before a word is read: a
   person writes on indigo, the agent answers on white paper, and a tool hop is
   machine output on a dark console so it stands apart from the prose. Your own
   messages keep the indigo gradient from chat-bubble-mine, which is the
   user-to-agent case seen from your side. */
.chat-bubble-other.chat-bubble-user-to-agent {
  background: linear-gradient(180deg, #f2f4ff 0%, #e8edff 100%);
  border-color: #d3dafc;
}
/* Tool input and output are code, so they are shown the way a terminal shows
   them: dark, quiet, and unmistakably not part of the answer. */
.chat-bubble-other.chat-bubble-tool-to-agent {
  background: #0f1729;
  border-color: #22304a;
  color: #cbd5e1;
  box-shadow: 0 12px 28px -16px rgba(2, 6, 23, 0.9);
}
/* An agent answering a person is the document: plain paper, so the prose and
   tables inside it stay the easiest thing on screen to read. */
.chat-bubble-other.chat-bubble-agent-to-user {
  background: #fff;
  border-color: #e4e8f2;
}
/* One agent handing work to the next is neither a person nor a tool. */
.chat-bubble-other.chat-bubble-agent-to-agent {
  background: #f5f3ff;
  border-color: #ddd6fe;
}
.chat-bubble-sender {
  display: inline-flex; align-items: center; gap: 0.3rem;
  font-size: 0.7rem; font-weight: 700;
  color: #4f46e5;
  margin-bottom: 0.3rem;
}
.chat-bubble-sender::before {
  content: '';
  width: 0.35rem; height: 0.35rem;
  border-radius: 9999px;
  background: currentColor;
}
.chat-debug-card {
  margin-bottom: 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.625rem;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06), 0 6px 16px -6px rgba(79, 70, 229, 0.18);
  overflow: hidden;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.chat-debug-head {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  width: 100%;
  padding: 0.4rem 0.6rem;
  border: 0;
  background: linear-gradient(135deg, #eef2ff 0%, #f8fafc 100%);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.chat-debug-head:hover { background: linear-gradient(135deg, #e5eaff 0%, #f1f4fb 100%); }
.chat-debug-headline {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  width: 100%;
}
.chat-debug-title {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: #4f46e5;
}
.chat-debug-title svg {
  color: #6366f1;
}
.chat-debug-chevron {
  flex-shrink: 0;
  color: #818cf8;
  transition: transform 0.15s;
}
.chat-debug-card.is-open .chat-debug-chevron { transform: rotate(180deg); }
/* Sender -> receiver on one truncated line instead of two stacked boxes. */
.chat-debug-route {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  min-width: 0;
  font-size: 0.62rem;
  color: #64748b;
}
.chat-debug-route-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 45%;
}
/* The hop the message took is the thing debug mode is read for, so the
   arrow carries the same indigo as the title instead of a tint that
   disappears into the header. */
.chat-debug-route-arrow { flex-shrink: 0; color: #4f46e5; }
.chat-debug-dot {
  width: 0.35rem;
  height: 0.35rem;
  border-radius: 9999px;
  background: #94a3b8;
  flex-shrink: 0;
}
.chat-debug-dot.is-user { background: #6366f1; }
.chat-debug-dot.is-agent { background: #8b5cf6; }
.chat-debug-dot.is-tool { background: #f59e0b; }
.chat-debug-dot.is-null { background: #cbd5e1; }
.chat-debug-id-chip {
  padding: 0.06rem 0.45rem;
  border-radius: 999px;
  background: #6366f1;
  color: #fff;
  font-size: 0.62rem;
  font-weight: 700;
  line-height: 1.3;
}
.chat-debug-badge {
  margin-left: auto;
  padding: 0.12rem 0.5rem;
  border-radius: 999px;
  background: rgba(99, 102, 241, 0.12);
  color: #4f46e5;
  font-size: 0.6rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.chat-debug-body {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 0.5rem 0.6rem;
  border-top: 1px solid #e6ebf7;
}
.chat-debug-actor {
  flex: 1;
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
  padding: 0.32rem 0.5rem;
  border-radius: 0.45rem;
  background: #f8fafc;
  border: 1px solid #eef2f7;
}
.chat-debug-actor-label {
  font-size: 0.54rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: #94a3b8;
}
.chat-debug-actor-name {
  font-size: 0.74rem;
  font-weight: 700;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chat-debug-actor-meta {
  font-size: 0.6rem;
  color: #64748b;
}
.chat-debug-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: center;
  flex-shrink: 0;
  color: #6366f1;
  line-height: 0;
}
.chat-debug-actor.is-user {
  border-color: #c7d2fe;
  background: #eef2ff;
}
.chat-debug-actor.is-user .chat-debug-actor-name { color: #4f46e5; }
.chat-debug-actor.is-user .chat-debug-actor-meta { color: #6d6af0; }
.chat-debug-actor.is-agent {
  border-color: #ddd6fe;
  background: #f5f3ff;
}
.chat-debug-actor.is-agent .chat-debug-actor-name { color: #7c3aed; }
.chat-debug-actor.is-agent .chat-debug-actor-meta { color: #8b5cf6; }
.chat-debug-actor.is-tool {
  border-color: #fde68a;
  background: #fffbeb;
}
.chat-debug-actor.is-tool .chat-debug-actor-name { color: #b45309; }
.chat-debug-actor.is-tool .chat-debug-actor-meta { color: #d97706; }
.chat-debug-actor.is-other {
  border-color: #cbd5e1;
  background: #f1f5f9;
}
.chat-debug-actor.is-other .chat-debug-actor-name { color: #475569; }
.chat-debug-actor.is-null {
  border-style: dashed;
}
.chat-debug-actor.is-null .chat-debug-actor-name { color: #94a3b8; }
.chat-debug-actor.is-null .chat-debug-actor-meta { color: #94a3b8; }
.chat-bubble-text { word-wrap: break-word; overflow-wrap: anywhere; }
.markdown-content :deep(p) { margin: 0 0 0.5rem; }
.markdown-content :deep(p:last-child) { margin-bottom: 0; }
.markdown-content :deep(li)::marker { color: #a5b4fc; }
.markdown-content :deep(hr) { border: 0; border-top: 1px solid #e5e7eb; margin: 0.6rem 0; }
.markdown-content :deep(img) { display: block; max-width: 100%; margin: 0.4rem 0; border-radius: 0.5rem; }
.markdown-content :deep(del) { opacity: 0.6; }
.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4) {
  margin: 0.4rem 0 0.3rem;
  font-size: 0.95rem;
  line-height: 1.25;
}
.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin: 0.35rem 0 0.45rem 1.1rem;
  padding: 0;
}
.markdown-content :deep(li) { margin: 0.15rem 0; }
.markdown-content :deep(blockquote) {
  margin: 0.45rem 0;
  padding-left: 0.65rem;
  border-left: 3px solid #c7d2fe;
  color: #4b5563;
}
.markdown-content :deep(code) {
  padding: 0.1rem 0.25rem;
  border-radius: 0.25rem;
  background: rgba(15, 23, 42, 0.08);
  font-family: Consolas, Monaco, monospace;
  font-size: 0.78rem;
}
.markdown-content :deep(pre) {
  max-width: 100%;
  /* Tool output can be thousands of characters; keep it scrollable so one
     debug message cannot push the rest of the conversation off screen. */
  max-height: 20rem;
  overflow: auto;
  margin: 0.45rem 0;
  padding: 0.65rem;
  border-radius: 0.5rem;
  background: #111827;
  color: #f9fafb;
}
.markdown-content :deep(pre code) {
  padding: 0;
  background: transparent;
  color: inherit;
}
.markdown-content :deep(a) { color: #4f46e5; text-decoration: underline; }
.markdown-content :deep(.md-muted) { color: #9ca3af; }
.markdown-content :deep(.md-table-wrap) {
  max-width: 100%;
  overflow-x: auto;
  margin: 0.35rem 0;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  background: #fff;
}
.markdown-content :deep(.md-data-table) {
  width: 100%;
  min-width: 420px;
  border-collapse: collapse;
  font-size: 0.76rem;
}
.markdown-content :deep(.md-data-table th),
.markdown-content :deep(.md-data-table td) {
  padding: 0.45rem 0.55rem;
  border-bottom: 1px solid #eef2f7;
  text-align: left;
  vertical-align: top;
  white-space: nowrap;
}
.markdown-content :deep(.md-data-table th) {
  background: #f8fafc;
  color: #475569;
  font-weight: 700;
  text-transform: capitalize;
}
.markdown-content :deep(.md-data-table tr:last-child td) { border-bottom: 0; }
.markdown-content :deep(.md-copy-btn) {
  /* Sticky: wide tables scroll sideways and the chip still has to be reachable. */
  position: sticky;
  left: 0;
  display: block;
  width: fit-content;
  margin: 0.4rem 0 0.25rem 0.4rem;
  padding: 0.1rem 0.45rem;
  font-size: 0.625rem;
  font-weight: 600;
  color: #4f46e5;
  background: #eef2ff;
  border: 1px solid #dbe2fb;
  border-radius: 9999px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.markdown-content :deep(.md-copy-btn:hover) { background: #e0e7ff; }
.markdown-content :deep(.md-copy-btn.is-copied) {
  color: #047857;
  background: #ecfdf5;
  border-color: #a7f3d0;
}
.chat-bubble-mine .markdown-content :deep(hr) { border-top-color: rgba(255, 255, 255, 0.3); }
.chat-bubble-mine .markdown-content :deep(.md-copy-btn) {
  color: #fff;
  background: rgba(255, 255, 255, 0.18);
  border-color: rgba(255, 255, 255, 0.32);
}
.chat-bubble-mine .markdown-content :deep(.md-copy-btn:hover) { background: rgba(255, 255, 255, 0.28); }
.chat-bubble-mine .markdown-content :deep(.md-copy-btn.is-copied) {
  background: rgba(16, 185, 129, 0.3);
  border-color: rgba(167, 243, 208, 0.6);
}
.chat-bubble-mine .markdown-content :deep(a) { color: #e0e7ff; }
/*
 * The table is the one markdown block that opts out of the own-bubble theme.
 * Its white card under the bubble's white text left the message looking empty,
 * and a tinted card still read differently from the same table in a received
 * message, so the card and everything on it return to the plain light theme.
 */
.chat-bubble-mine .markdown-content :deep(.md-table-wrap) {
  background: #fff;
  border-color: #e5e7eb;
  color: #1f2937;
}
.chat-bubble-mine .markdown-content :deep(.md-table-wrap .md-data-table th) {
  background: #f8fafc;
  color: #475569;
}
.chat-bubble-mine .markdown-content :deep(.md-table-wrap .md-data-table td) {
  border-bottom-color: #eef2f7;
}
.chat-bubble-mine .markdown-content :deep(.md-table-wrap .md-muted) { color: #9ca3af; }
.chat-bubble-mine .markdown-content :deep(.md-table-wrap a) { color: #4f46e5; }
.chat-bubble-mine .markdown-content :deep(.md-table-wrap code) {
  background: rgba(15, 23, 42, 0.08);
  color: #1f2937;
}
.chat-bubble-mine .markdown-content :deep(.md-table-wrap .md-copy-btn) {
  color: #4f46e5;
  background: #eef2ff;
  border-color: #dbe2fb;
}
.chat-bubble-mine .markdown-content :deep(.md-table-wrap .md-copy-btn:hover) { background: #e0e7ff; }
.chat-bubble-mine .markdown-content :deep(.md-table-wrap .md-copy-btn.is-copied) {
  color: #047857;
  background: #ecfdf5;
  border-color: #a7f3d0;
}
.chat-bubble-mine .markdown-content :deep(.md-muted) { color: rgba(255,255,255,0.65); }
.chat-bubble-mine .markdown-content :deep(blockquote) {
  border-left-color: rgba(255,255,255,0.55);
  color: rgba(255,255,255,0.86);
}
/* Everything inside a tool bubble is restyled for the dark surface: the debug
   card becomes an inset panel and markdown switches to light-on-dark. */
.chat-bubble-tool-to-agent .chat-bubble-sender { color: #a5b4fc; }
.chat-bubble-tool-to-agent .chat-bubble-time { color: rgba(203, 213, 225, 0.5); }
.chat-bubble-tool-to-agent .chat-debug-card {
  background: rgba(148, 163, 184, 0.07);
  border-color: rgba(148, 163, 184, 0.2);
  box-shadow: none;
}
.chat-bubble-tool-to-agent .chat-debug-head {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.3) 0%, rgba(15, 23, 41, 0) 100%);
}
.chat-bubble-tool-to-agent .chat-debug-head:hover {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.45) 0%, rgba(15, 23, 41, 0.05) 100%);
}
.chat-bubble-tool-to-agent .chat-debug-title { color: #c7d2fe; }
.chat-bubble-tool-to-agent .chat-debug-title svg { color: #a5b4fc; }
.chat-bubble-tool-to-agent .chat-debug-chevron { color: #818cf8; }
.chat-bubble-tool-to-agent .chat-debug-badge {
  background: rgba(148, 163, 184, 0.16);
  color: #cbd5e1;
}
.chat-bubble-tool-to-agent .chat-debug-route { color: #94a3b8; }
.chat-bubble-tool-to-agent .chat-debug-route-arrow { color: #a5b4fc; }
.chat-bubble-tool-to-agent .chat-debug-body { border-top-color: rgba(148, 163, 184, 0.16); }
.chat-bubble-tool-to-agent .chat-debug-actor {
  background: rgba(148, 163, 184, 0.07);
  border-color: rgba(148, 163, 184, 0.16);
}
.chat-bubble-tool-to-agent .chat-debug-actor-label { color: #64748b; }
.chat-bubble-tool-to-agent .chat-debug-actor-name { color: #e2e8f0; }
.chat-bubble-tool-to-agent .chat-debug-actor-meta { color: #94a3b8; }
.chat-bubble-tool-to-agent .chat-debug-arrow { color: #818cf8; }
.chat-bubble-tool-to-agent .chat-debug-actor.is-user {
  background: rgba(99, 102, 241, 0.24);
  border-color: rgba(129, 140, 248, 0.42);
}
.chat-bubble-tool-to-agent .chat-debug-actor.is-user .chat-debug-actor-name { color: #c7d2fe; }
.chat-bubble-tool-to-agent .chat-debug-actor.is-user .chat-debug-actor-meta { color: #a5b4fc; }
.chat-bubble-tool-to-agent .chat-debug-actor.is-agent {
  background: rgba(139, 92, 246, 0.22);
  border-color: rgba(167, 139, 250, 0.42);
}
.chat-bubble-tool-to-agent .chat-debug-actor.is-agent .chat-debug-actor-name { color: #ddd6fe; }
.chat-bubble-tool-to-agent .chat-debug-actor.is-agent .chat-debug-actor-meta { color: #c4b5fd; }
.chat-bubble-tool-to-agent .markdown-content :deep(p),
.chat-bubble-tool-to-agent .markdown-content :deep(li),
.chat-bubble-tool-to-agent .markdown-content :deep(td) { color: #cbd5e1; }
.chat-bubble-tool-to-agent .markdown-content :deep(h1),
.chat-bubble-tool-to-agent .markdown-content :deep(h2),
.chat-bubble-tool-to-agent .markdown-content :deep(h3),
.chat-bubble-tool-to-agent .markdown-content :deep(h4),
.chat-bubble-tool-to-agent .markdown-content :deep(strong) { color: #f1f5f9; }
.chat-bubble-tool-to-agent .markdown-content :deep(pre) {
  background: #0a101f;
  border: 1px solid rgba(148, 163, 184, 0.16);
  color: #e2e8f0;
}
.chat-bubble-tool-to-agent .markdown-content :deep(code) {
  background: rgba(148, 163, 184, 0.16);
  color: #e2e8f0;
}
.chat-bubble-tool-to-agent .markdown-content :deep(a) { color: #93c5fd; }
.chat-bubble-tool-to-agent .markdown-content :deep(hr) { border-top-color: rgba(148, 163, 184, 0.18); }
.chat-bubble-tool-to-agent .markdown-content :deep(li)::marker { color: #818cf8; }
.chat-bubble-tool-to-agent .markdown-content :deep(blockquote) {
  border-left-color: #6366f1;
  color: #94a3b8;
}
.chat-bubble-tool-to-agent .markdown-content :deep(.md-muted) { color: #64748b; }
.chat-bubble-tool-to-agent .markdown-content :deep(.md-table-wrap) {
  border-color: rgba(148, 163, 184, 0.18);
  background: rgba(148, 163, 184, 0.05);
}
.chat-bubble-tool-to-agent .markdown-content :deep(.md-data-table th) {
  background: rgba(148, 163, 184, 0.12);
  color: #cbd5e1;
}
.chat-bubble-tool-to-agent .markdown-content :deep(.md-data-table td) {
  border-bottom-color: rgba(148, 163, 184, 0.13);
}
.chat-bubble-tool-to-agent .markdown-content :deep(.md-copy-btn) {
  color: #c7d2fe;
  background: rgba(99, 102, 241, 0.22);
  border-color: rgba(129, 140, 248, 0.38);
}
.chat-bubble-tool-to-agent .markdown-content :deep(.md-copy-btn:hover) { background: rgba(99, 102, 241, 0.34); }
.chat-bubble-tool-to-agent .markdown-content :deep(.md-copy-btn.is-copied) {
  color: #6ee7b7;
  background: rgba(16, 185, 129, 0.2);
  border-color: rgba(52, 211, 153, 0.4);
}
.chat-bubble-time {
  display: block;
  font-size: 0.625rem;
  color: #9ca3af;
  margin-top: 0.3rem;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.chat-bubble-mine .chat-bubble-time { color: rgba(255, 255, 255, 0.72); }
.chat-empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
  font-size: 0.875rem; color: #9ca3af;
}
.chat-typing-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.75rem;
  font-size: 0.8125rem;
  color: #6b7280;
}
.chat-typing-dots { display: flex; gap: 3px; align-items: center; }
.chat-typing-dots span {
  width: 6px; height: 6px; border-radius: 50%; background: #9ca3af;
  animation: typingBounce 1.4s infinite ease-in-out both;
}
.chat-typing-dots span:nth-child(1) { animation-delay: -0.32s; }
.chat-typing-dots span:nth-child(2) { animation-delay: -0.16s; }
.chat-typing-dots span:nth-child(3) { animation-delay: 0s; }
@keyframes typingBounce {
  0%, 80%, 100% { transform: scale(0.6); }
  40% { transform: scale(1); }
}
.chat-input-area {
  display: flex; gap: 0.5rem;
  padding: 0.75rem;
  border-top: 1px solid #e5e7eb;
  background: #fff;
  flex-shrink: 0;;
}
.chat-input {
  flex: 1; padding: 0.5rem 0.625rem;
  border: 1px solid #d1d5db;
  border-radius: 0.5rem; font-size: 0.8125rem;
  outline: none; resize: none;
  background: #fff; color: #111827;
}
.chat-input:focus { border-color: #6366f1; box-shadow: 0 0 0 2px #c7d2fe; }
.chat-send-btn {
  padding: 0.5rem 1rem; border-radius: 0.5rem;
  font-size: 0.8125rem; font-weight: 600;
  background: #6366f1; color: #fff;
  border: none; cursor: pointer;
  white-space: nowrap;
}
.chat-send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.chat-send-btn:hover:not(:disabled) { background: #4f46e5; }
.chat-stop-btn { background: #dc2626; }
.chat-stop-btn:hover:not(:disabled) { background: #b91c1c; }

/* Chat card styles */
.chat-card-wrapper {
  display: flex; align-items: center;
  padding: 0.5rem 0.625rem;
  border: 1px solid transparent;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.1s;
}
.chat-card-wrapper:hover { background: #f9fafb; }
.chat-card-selected {
  background: #eef2ff;
  border-color: #a5b4fc;
}
.chat-card-top-row { display: flex; align-items: center; gap: 0.5rem; width: 100%; }
.chat-card-avatar {
  width: 2rem; height: 2rem;
  display: flex; align-items: center; justify-content: center;
  background: #f3f4f6;
  border-radius: 50%;
  flex-shrink: 0;
  color: #6b7280;
}
.chat-card-info { flex: 1; min-width: 0; }
.chat-card-name {
  font-size: 0.8125rem; font-weight: 500;
  color: #111827;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.chat-card-meta { margin-top: 0.125rem; }
.chat-card-new-badge {
  font-size: 0.6875rem; font-weight: 600;
  background: #6366f1; color: #fff;
  padding: 0.125rem 0.375rem;
  border-radius: 9999px;
}
.chat-card-actions {
  display: flex; gap: 0.125rem;
  flex-shrink: 0;
}
.chat-card-btn {
  width: 1.5rem; height: 1.5rem;
  display: flex; align-items: center; justify-content: center;
  border: none; background: transparent;
  color: #9ca3af; cursor: pointer;
  border-radius: 0.25rem;
}
.chat-card-btn:hover { color: #4f46e5; background: #eef2ff; }
.chat-card-btn-danger:hover { color: #dc2626; background: #fef2f2; }
.chat-loading-spinner-sm {
  animation: spin 0.7s linear infinite;
  color: #6366f1;
}

/* Flow canvas */
.projects-panel-flow { display: flex; flex-direction: column; width: 100%; flex: 1; min-height: 0; }
.projects-panel-tabledata {
  flex: 0 0 45%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.projects-table-data-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.projects-data-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.75rem;
}
.projects-data-grid th,
.projects-data-grid td {
  border: 1px solid #e5e7eb;
  padding: 0.35rem 0.5rem;
  text-align: left;
  white-space: nowrap;
  max-width: 16rem;
  overflow: hidden;
  text-overflow: ellipsis;
}
.projects-data-grid th {
  background: #f9fafb;
  color: #374151;
  font-weight: 600;
  position: sticky;
  top: 0;
}
.projects-data-grid th.sortable {
  cursor: pointer;
  user-select: none;
}
.projects-data-grid th.sortable:hover {
  color: #1e40af;
}
.projects-data-grid th.sortable.sorted {
  color: #2563eb;
}
.sort-arrow {
  display: inline-flex;
  vertical-align: middle;
  margin-left: 0.2rem;
}
.sort-arrow svg {
  width: 0.72rem;
  height: 0.72rem;
}
th.sortable.sorted .sort-arrow {
  color: #2563eb;
}
.projects-data-grid .row-id {
  color: #9ca3af;
}
.projects-data-grid th.projects-data-actions,
.projects-data-grid td.projects-data-actions {
  width: 5rem;
  max-width: 5rem;
  vertical-align: middle;
  text-align: center;
}
.projects-data-grid td.projects-data-actions .projects-action-btn {
  display: inline-flex;
  vertical-align: middle;
  margin: 0 0.15rem;
}
.projects-data-toolbar {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
}
.projects-data-btn {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.28rem 0.6rem;
  border-radius: 0.375rem;
  border: 1px solid #d1d5db;
  background: #fff;
  color: #374151;
  cursor: pointer;
  transition: all 0.1s;
  white-space: nowrap;
}
.projects-data-btn:hover:not(:disabled) { background: #f3f4f6; border-color: #9ca3af; }
.projects-data-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.projects-data-btn-primary {
  border-color: #a5b4fc;
  background: #eef2ff;
  color: #4f46e5;
}
.projects-data-btn-primary:hover:not(:disabled) { background: #e0e7ff; }
.projects-data-btn-danger {
  border-color: #fca5a5;
  background: #fef2f2;
  color: #dc2626;
}
.projects-data-btn-danger:hover:not(:disabled) { background: #fee2e2; }
.projects-data-check {
  width: 2.25rem;
  text-align: center;
}
.projects-data-check input[type="checkbox"] {
  width: 0.95rem;
  height: 0.95rem;
  accent-color: #4f46e5;
  cursor: pointer;
  vertical-align: middle;
}
.projects-alert {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  margin: 0 0.75rem;
}
.projects-toast {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 1200;
  background: #10b981;
  color: #fff;
  padding: 0.6rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
}
.projects-textarea {
  min-height: 5rem;
  resize: vertical;
  font-family: inherit;
}
.projects-modal-lg {
  max-width: 40rem;
}
.projects-help {
  font-size: 0.8125rem;
  color: #6b7280;
  margin: 0;
}
.projects-file-name {
  font-size: 0.8125rem;
  color: #4f46e5;
  margin: 0;
  word-break: break-all;
}
.projects-mapping-panel {
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  overflow: hidden;
}
.projects-mapping-header {
  display: flex;
  gap: 1rem;
  padding: 0.5rem 0.75rem;
  background: #f9fafb;
  font-size: 0.75rem;
  font-weight: 600;
  color: #6b7280;
}
.projects-mapping-header span { flex: 1; }
.projects-mapping-row {
  display: flex;
  gap: 1rem;
  padding: 0.6rem 0.75rem;
  border-top: 1px solid #e5e7eb;
  align-items: flex-start;
}
.projects-mapping-db-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.projects-mapping-db-col strong { font-size: 0.8125rem; color: #111827; }
.projects-mapping-db-col span { font-size: 0.72rem; color: #9ca3af; }
.projects-mapping-select-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.projects-mapping-sample {
  font-size: 0.72rem;
  color: #6b7280;
  word-break: break-word;
}
.flow-header { flex-shrink: 0; }
/* Narrow columns wrap the toolbar instead of clipping the zoom controls. */
.flow-toolbar { display: flex; align-items: center; gap: 0.25rem; flex-wrap: wrap; }
.flow-btn {
        padding: 0.35rem;
        border: 1px solid #e2e7f6;
        border-radius: 0.375rem;
        background: #fff;
        color: #4a5268;
        cursor: pointer;
        font-size: 0.75rem;
        font-weight: 500;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        line-height: 1;
        transition: background 0.15s, border-color 0.15s, color 0.15s;
    }

    .flow-btn:hover { background: #f4f6fd; border-color: #c7d2fe; color: #3730a3; }
    .flow-btn:disabled { opacity: 0.5; cursor: not-allowed; }

    .flow-btn-add {
        background: #eef2ff;
        color: #4338ca;
        border-color: #c7d2fe;
    }
    .flow-btn-add:hover { background: #e0e7ff; color: #3730a3; }

    .flow-btn-reload {
        background: #f8fafc;
        color: #475569;
        border-color: #e2e8f0;
    }
    .flow-btn-reload:hover { background: #eef1f7; color: #334155; }

    .flow-btn-save {
        background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
        color: #fff;
        border-color: transparent;
        box-shadow: 0 2px 6px rgba(79, 70, 229, 0.35);
    }
    .flow-btn-save:hover { background: linear-gradient(135deg, #5457e5 0%, #4338ca 100%); color: #fff; }
.flow-separator {
        width: 1px;
        height: 1.25rem;
        background: #e2e7f6;
        align-self: center;
    }
.flow-zoom-level {
        font-size: 0.75rem;
        font-weight: 500;
        color: #6b7488;
        min-width: 3rem;
        text-align: center;
        align-self: center;
    }
.flow-svg {
        width: 100%;
        height: 100%;
        display: block;
        overflow: visible;
    }
.flow-placeholder { display: flex; align-items: center; justify-content: center; height: 100%; }
.flow-empty { font-size: 0.875rem; color: #9ca3af; }
/* Nodes, wires and ports are built dynamically, so they never carry this
   component's scope attribute. Their styles are in the unscoped block at the
   end of this file, which is the single place the canvas palette lives. */

/* Overlay / Modal */
.projects-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center;
  padding: 1rem;
}
.projects-modal {
  background: #fff;
  border-radius: 0.75rem;
  width: 100%; max-width: 28rem;
  max-height: 90vh; overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,0.15);
}
.projects-agent-modal {
  max-width: 42rem;
}
.projects-modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #e5e7eb;
}
.projects-modal-header h3 { margin: 0; font-size: 1rem; font-weight: 600; color: #111827; }
.projects-modal-close {
  width: 2rem; height: 2rem; display: flex; align-items: center; justify-content: center;
  border: none; background: transparent; font-size: 1.5rem;
  color: #9ca3af; cursor: pointer; border-radius: 0.375rem;
}
.projects-modal-close:hover { background: #f3f4f6; color: #4b5563; }
.projects-modal-body { padding: 1.25rem; display: flex; flex-direction: column; gap: 1rem; }
.projects-modal-footer {
  display: flex; justify-content: flex-end; gap: 0.5rem;
  padding: 1rem 1.25rem;
  border-top: 1px solid #e5e7eb;
}
.projects-field { display: flex; flex-direction: column; gap: 0.25rem; }
.projects-field span { font-size: 0.8125rem; font-weight: 500; color: #374151; }
.projects-field-checkbox { flex-direction: row; align-items: center; gap: 0.5rem; }
.projects-input {
  width: 100%; padding: 0.5rem 0.625rem;
  border: 1px solid #d1d5db;
  border-radius: 0.5rem; font-size: 0.875rem;
  outline: none; box-sizing: border-box;
  background: #fff; color: #111827;
}
.projects-input:focus { border-color: #6366f1; box-shadow: 0 0 0 2px #c7d2fe; }
.projects-checkbox { width: 1rem; height: 1rem; cursor: pointer; }
.projects-skill-picker {
  max-height: 13rem;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  background: #fff;
}
.projects-skill-option {
  min-height: 2.75rem;
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.625rem 0.75rem;
  border-bottom: 1px solid #e5e7eb;
  cursor: pointer;
}
.projects-skill-option:last-child { border-bottom: 0; }
.projects-skill-option:hover { background: #f9fafb; }
.projects-skill-empty {
  color: #9ca3af;
  cursor: default;
}
.projects-skill-main {
  min-width: 0;
  display: grid;
  gap: 0.125rem;
}
.projects-skill-main span {
  overflow: hidden;
  color: #111827;
  font-size: 0.8125rem;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.projects-skill-main small {
  overflow: hidden;
  color: #6b7280;
  font-size: 0.75rem;
  font-weight: 400;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.projects-generator-input {
  min-height: 6rem;
  resize: vertical;
}
.projects-field-hint { color: #6b7280; font-size: 0.75rem; font-weight: 400; }
.projects-context-empty { margin: 0; color: #9ca3af; font-size: 0.75rem; }
.projects-context-row {
  display: grid; gap: 0.375rem;
  padding: 0.625rem; margin-top: 0.375rem;
  border: 1px solid #e5e7eb; border-radius: 0.5rem;
  background: #f9fafb;
}
.projects-context-head { display: flex; align-items: center; gap: 0.5rem; }
.projects-context-name {
  flex: 1; min-width: 0; overflow: hidden;
  color: #111827; font-size: 0.8125rem; font-weight: 600;
  text-overflow: ellipsis; white-space: nowrap;
}
.projects-context-inactive {
  flex: 0 0 auto; padding: 0.0625rem 0.375rem; border-radius: 999px;
  background: #fee2e2; color: #b91c1c;
  font-size: 0.6875rem; font-weight: 600;
}
.projects-context-remove {
  flex: 0 0 auto; padding: 0 0.25rem;
  border: none; background: transparent; cursor: pointer;
  color: #9ca3af; font-size: 1.125rem; line-height: 1;
}
.projects-context-remove:hover { color: #dc2626; }
.projects-context-args {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.8125rem;
}
.projects-context-add { display: flex; gap: 0.375rem; margin-top: 0.5rem; }
.projects-context-add select { min-width: 0; }
.projects-context-add .projects-btn { flex: 0 0 auto; min-width: 2.25rem; }
.projects-context-add .projects-btn:disabled { opacity: 0.5; cursor: default; }
.projects-btn {
  padding: 0.5rem 1rem; border-radius: 0.5rem;
  display: inline-flex; align-items: center; justify-content: center; gap: 0.45rem;
  font-size: 0.8125rem; font-weight: 600;
  cursor: pointer; border: none; transition: all 0.1s;
}
.projects-btn-cancel { background: #f3f4f6; color: #374151; }
.projects-btn-cancel:hover { background: #e5e7eb; }
.projects-btn-save { background: #6366f1; color: #fff; }
.projects-btn-save:hover { background: #4f46e5; }
.generate-btn { min-width: 124px; }
.generate-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 999px;
  animation: generate-spin 0.7s linear infinite;
}

@keyframes generate-spin {
  to { transform: rotate(360deg); }
}

@keyframes spin { to { transform: rotate(360deg); } }
.flow-canvas {
        flex: 1;
        position: relative;
        overflow: hidden;
        min-height: 0;
        user-select: none;
        border-radius: 0 0 0.75rem 0.75rem;
        /* Soft indigo wash with a faint dot grid so nodes sit on a surface
           instead of a flat grey block. */
        background-color: #f7f8fd;
        background-image:
            radial-gradient(circle at 1px 1px, #d9dff5 1px, transparent 0),
            linear-gradient(160deg, #f9fafe 0%, #eef1fa 100%);
        background-size: 22px 22px, 100% 100%;
    }
.flow-loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(247, 248, 253, 0.85);
  z-index: 10;
}
.flow-loading-spinner {
  width: 2rem;
  height: 2rem;
  border: 3px solid #e0e4f5;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
.btn-loading-spinner { animation: spin 0.7s linear infinite; }

/* Draggable agent items — custom grab cursors with black outline */
.projects-item-wrapper[draggable='true'] {
  cursor: url('data:image/svg+xml,\<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2224%22 height=%2224%22 viewBox=%220 0 24 24%22%3E\<path d=%22M9 11V6a1.5 1.5 0 0 1 3 0v4M12 6a1.5 1.5 0 0 1 3 0v4M15 6a1.5 1.5 0 0 1 3 1.5V13a6 6 0 0 1-12 0v-3a1.5 1.5 0 0 1 3 0v1%22 fill=%22%23fff%22 stroke=%22%23000%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22 /%3E\</svg%3E') 12 12, grab !important;
}
.projects-item-wrapper[draggable='true']:active {
  cursor: url('data:image/svg+xml,\<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2224%22 height=%2224%22 viewBox=%220 0 24 24%22%3E\<path d=%22M9 10V4a1.5 1.5 0 0 1 3 0v4M12 6a1.5 1.5 0 0 1 3 0v4M15 6a1.5 1.5 0 0 1 3 1.5V13a6 6 0 0 1-12 0v-3a1.5 1.5 0 0 1 3 0v1%22 fill=%22%23e5e7eb%22 stroke=%22%23000%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22 /%3E\</svg%3E') 12 12, grabbing !important;
}
/* The phone step bar only exists below 768px; see the media query. */
.mobile-stepbar { display: none; }

/* Phone layout: the five columns want ~1200px, so a phone shows one at a time
   instead of a sideways-scrolling row of clipped panels. The step bar keeps
   the way back one tap away, and the visible pane takes the rest of the height
   so each panel keeps its own scroller. */
@media (max-width: 767px) {
  .projects-layout {
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow-x: hidden;
    padding: 0.75rem;
    gap: 0.75rem;
  }

  .mobile-pane-hidden { display: none !important; }

  .projects-col,
  .projects-col-chat,
  .projects-col-flow {
    flex: 1 1 0;
    height: auto;
    min-height: 0;
  }

  .mobile-stepbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    flex: 0 0 auto;
  }
  .mobile-step-tabs { display: inline-flex; gap: 0.25rem; }
  .mobile-step-back,
  .mobile-step-tabs button {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.35rem 0.6rem;
    font-size: 0.78rem;
    font-weight: 600;
    color: #4b5563;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 0.6rem;
    cursor: pointer;
  }
  .mobile-step-back { color: #4338ca; }
  .mobile-step-back:hover,
  .mobile-step-tabs button:hover { background: #f9fafb; }
  .mobile-step-tabs button.is-active {
    color: #4338ca;
    background: #eef2ff;
    border-color: #c7d2fe;
  }
  .mobile-step-tabs button.is-active:hover { background: #e0e7ff; }

  /* A table needs the whole width of a phone, so a bubble holding one stops
     insetting itself and lets the table's own scroller do the work. */
  .chat-bubble:has(.md-table-wrap) {
    max-width: 100%;
  }
}

</style>

<!-- Unscoped: flow SVG styles apply to dynamically-created elements -->
<style>
/* Workflow palette: indigo/slate surfaces with mint and rose pills, soft
   shadows and rounded cards, so the canvas reads as one designed piece.
   The gradient fills for start/stop are set in drawNode() because a CSS fill
   would override the presentation attribute. */
.flow-node-group { fill: #ffffff; stroke: #c7d2fe; stroke-width: 1.5; rx: 14; ry: 14; }
.flow-node-text { font-size: 11px; fill: #1f2937; text-anchor: middle; dominant-baseline: central; pointer-events: none; }
.flow-node-text-title { font-weight: 700; font-size: 12px; fill: #ffffff; letter-spacing: 0.02em; }
.flow-port { cursor: crosshair; fill: #ffffff; stroke: #bfcbf5; stroke-width: 1.5; }
.flow-port:hover { fill: #6366f1; stroke: #4f46e5; }
.flow-wire, .flow-wire-path { fill: none; stroke: #c3cdf2; stroke-width: 2; stroke-linecap: round; pointer-events: none; }
.flow-wire-drag { fill: none; stroke: #6366f1; stroke-width: 2; stroke-dasharray: 6,4; stroke-linecap: round; pointer-events: none; }
.flow-delete-btn { cursor: pointer; fill: #e11d48; font-size: 12px; text-anchor: middle; dominant-baseline: central; }

.projects-modal-tabs {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}
.projects-modal-tabs button {
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #475569;
  border-radius: 6px;
  padding: 0.3rem 0.7rem;
  font-size: 0.8rem;
  cursor: pointer;
}
.projects-modal-tabs button:hover {
  border-color: #94a3b8;
}
.projects-modal-tabs button.active {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}
</style>
