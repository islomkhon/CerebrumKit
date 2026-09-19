<template>
  <div class="projects-layout" :class="{ 'projects-layout-single': !showProjectColumn }">
    <!-- Column 1: Projects (hidden when the client has a single project) -->
    <div
      v-if="showProjectColumn"
      class="projects-col projects-col-projects"
      :class="{ 'mobile-pane-hidden': mobilePane === 'chat' }"
    >
      <div class="projects-panel">
        <div class="projects-panel-header">
          <div class="projects-panel-title-row">
            <h2 class="projects-panel-title">{{ t('client.projects.title') }}</h2>
          </div>
          <div class="projects-search-row">
            <input
              v-model="projectSearch"
              type="text"
              :placeholder="t('client.projects.search_placeholder')"
              class="projects-search"
            />
          </div>
        </div>
        <div class="projects-list">
          <div v-if="loadingProjects" class="projects-empty">
            <div class="loading-spinner"></div>
          </div>
          <div v-else-if="filteredProjects.length === 0" class="projects-empty">
            {{ t('client.projects.no_projects') }}
          </div>
          <div
            v-for="p in filteredProjects"
            :key="p.id"
            class="projects-item-wrapper"
            :class="{ 'projects-item-selected': selectedProjectId === p.id }"
            @click="selectProject(p)"
          >
            <div class="projects-item-content">
              <div class="projects-item-name">{{ p.name }}</div>
              <div v-if="p.description" class="projects-item-meta">
                <span class="projects-item-desc">{{ p.description }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Column 2: Chats -->
    <div class="projects-col projects-col-chats" :class="{ 'mobile-pane-hidden': mobilePane === 'chat' }">
      <div class="projects-panel">
        <div class="projects-panel-header">
          <div class="projects-panel-title-row">
            <h2 class="projects-panel-title">{{ t('client.chat.title') }}</h2>
            <button v-if="selectedProjectId" class="projects-add-btn" @click="openCreateChatModal">
              {{ t('client.chat.new') }}
            </button>
          </div>
        </div>
        <div class="projects-list">
          <div v-if="!selectedProjectId" class="projects-empty">
            <span class="loading-spinner"></span>
          </div>
          <div v-else-if="loadingChats" class="projects-empty">
            <div class="loading-spinner"></div>
          </div>
          <div v-else-if="chats.length === 0" class="projects-empty">
            {{ t('client.chat.no_chats') }}
          </div>
          <div
            v-for="c in chats"
            :key="c.id"
            class="chat-card-wrapper"
            :class="{ 'chat-card-selected': selectedChatId === c.id }"
            @click="openChat(c)"
          >
            <div class="chat-card-top-row">
              <div class="chat-card-avatar">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1.25rem;height:1.25rem"><path stroke-linecap="round" stroke-linejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155"/></svg>
              </div>
              <div class="chat-card-info">
                <div class="chat-card-name">{{ c.description || t('client.chat.no_description') }}</div>
              </div>
              <div class="chat-card-actions" @click.stop>
                <button class="chat-card-btn" @click="openEditChatModal" :title="t('client.chat.edit')">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" /></svg>
                </button>
                <button class="chat-card-btn chat-card-btn-danger" @click="deleteChat" :title="t('client.chat.delete')">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:1rem;height:1rem"><path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Column 3: Conversation -->
    <div class="projects-col projects-col-chat" :class="{ 'mobile-pane-hidden': mobilePane === 'list' }">
      <div class="projects-panel chat-panel">
        <template v-if="selectedChatId">
          <div class="projects-panel-header chat-header">
            <div class="projects-panel-title-row chat-header-row">
              <button
                type="button"
                class="chat-back-btn"
                :aria-label="t('client.chat.back')"
                @click="mobilePane = 'list'"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" /></svg>
              </button>
              <h2 class="projects-panel-title chat-header-title">{{ selectedChat?.description || t('client.chat.no_description') }}</h2>
            </div>
          </div>
          <div
            class="chat-messages"
            ref="messagesContainer"
            @click="onMessagesClick"
            @scroll.passive="onMessagesScroll"
          >
            <div v-if="loadingOlderMessages" class="chat-load-older">
              <div class="loading-spinner"></div>
            </div>
            <div v-if="loadingMessages" class="projects-empty">
              <div class="loading-spinner"></div>
            </div>
            <div v-else-if="visibleMessages.length === 0" class="chat-empty">{{ t('client.chat.no_messages') }}</div>
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
                <div class="chat-bubble" :class="isOwnMessage(msg) ? 'chat-bubble-mine' : 'chat-bubble-other'">
                  <div v-if="showSender(idx)" class="chat-bubble-sender">{{ msg.sender_name || msg.sender_type }}</div>
                  <div class="chat-bubble-text markdown-content" v-html="renderMarkdown(msg.content, { copyLabel: t('client.chat.copy_table') })"></div>
                  <span class="chat-bubble-time">{{ new Date(msg.created_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) }}</span>
                </div>
              </div>
            </template>
            <div v-if="typingUser" class="chat-typing-indicator">
              <span class="chat-typing-dots"><span></span><span></span><span></span></span>
              <span class="chat-typing-text">{{ t('client.chat.typing', { name: typingUser }) }}</span>
            </div>
          </div>
          <div class="chat-input-area">
            <textarea
              v-model="newMessageContent"
              :placeholder="t('client.chat.type_message')"
              class="chat-input"
              :readonly="agentLoopRunning"
              @keydown.enter.exact.prevent="sendMessage"
              rows="2"
            ></textarea>
            <button
              class="chat-send-btn"
              :class="{ 'chat-stop-btn': agentLoopRunning }"
              @click="agentLoopRunning ? stopAgentLoop() : sendMessage()"
              :disabled="agentLoopStopping || (!agentLoopRunning && (sending || !newMessageContent.trim()))"
            >
              {{ agentLoopRunning ? (agentLoopStopping ? 'Stopping...' : 'Stop') : t('client.chat.send') }}
            </button>
          </div>
        </template>
        <template v-else>
          <div class="chat-empty">{{ t('admin.projects.loading') }}</div>
        </template>
      </div>
    </div>

    <!-- Create Chat Modal -->
    <div v-if="showCreateChatModal" class="modal-overlay" @click.self="closeCreateChatModal">
      <div class="modal">
        <h3>{{ t('client.chat.create_title') }}</h3>
        <div class="modal-body">
          <label>{{ t('client.chat.create_description') }}</label>
          <input v-model="newChatDescription" type="text" class="form-input" />
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="closeCreateChatModal">{{ t('admin.projects.cancel') }}</button>
          <button class="btn btn-primary" @click="createChat" :disabled="!newChatDescription.trim()">
            {{ t('client.chat.create_btn') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Edit Chat Modal -->
    <div v-if="showEditChatModal" class="modal-overlay" @click.self="closeEditChatModal">
      <div class="modal">
        <h3>{{ t('client.chat.edit') }}</h3>
        <div class="modal-body">
          <label>{{ t('client.chat.edit_description') }}</label>
          <input v-model="editChatDescription" type="text" class="form-input" />
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="closeEditChatModal">{{ t('admin.projects.cancel') }}</button>
          <button class="btn btn-primary" @click="saveChatEdit" :disabled="!editChatDescription.trim()">
            {{ t('admin.projects.save') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../../stores/auth'
import {
  fetchClientProjects,
  fetchClientChats,
  createClientChat,
  updateClientChat,
  deleteClientChat,
  fetchClientChatMessages,
  sendClientChatMessage,
} from '../../api/chats'
import type { Project, Chat, Message } from '../../types'
import { renderMarkdown } from '../../utils/markdown'
import { WS_BASE_URL } from '../../api/baseUrl'

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
  return projects.value.filter(p =>
    p.name.toLowerCase().includes(q) ||
    (p.description && p.description.toLowerCase().includes(q))
  )
})

// A client owning a single project has nothing to choose from, so the projects
// column is hidden and the chat list expands into its place.
const showProjectColumn = computed(() => projects.value.length !== 1)

// ── Chats ──
const chats = ref<Chat[]>([])
const selectedChatId = ref<number | null>(null)
const loadingChats = ref(false)

// A phone is too narrow for the chat list and the conversation side by side, so
// the panel shows one at a time: the list first, then the conversation the
// client taps into, with the back button in the chat header returning to the
// list. On a wide screen both panes are on screen and this has no effect.
const mobilePane = ref<'list' | 'chat'>('list')

const selectedChat = computed(() => chats.value.find(c => c.id === selectedChatId.value) || null)

// ── Messages ──
const messages = ref<Message[]>([])
// Clients only see real chat messages. Internal "flow" messages (how the input
// passed between agents) and "tool" messages (tool input/output) stay hidden.
const visibleMessages = computed(() =>
  messages.value.filter(
    (msg) => msg.message_type !== 'flow' && msg.message_type !== 'tool',
  ),
)

// Consecutive messages from one sender read as a single run: the sender is
// printed once, on the run's first bubble, and the bubbles stack closer.
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
  const msg = visibleMessages.value[index]
  if (!msg || isOwnMessage(msg)) return false
  return !continuesPreviousRun(index)
}

function isGroupedWithPrevious(index: number) {
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
  button.textContent = t('client.chat.copied')
  button.classList.add('is-copied')
  setTimeout(() => {
    button.textContent = t('client.chat.copy_table')
    button.classList.remove('is-copied')
  }, 1600)
}

const loadingMessages = ref(false)
const newMessageContent = ref('')
const sending = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)
const typingUser = ref<string | null>(null)
const agentLoopRunning = ref(false)
const agentLoopStopping = ref(false)
let typingTimer: ReturnType<typeof setTimeout> | null = null

// ── Create Chat ──
const showCreateChatModal = ref(false)
const newChatDescription = ref('')

// ── Edit Chat ──
const showEditChatModal = ref(false)
const editChatDescription = ref('')

// ── WebSocket ──
let chatSocket: WebSocket | null = null

// ── Lifecycle ──
onMounted(async () => {
  loadingProjects.value = true
  try {
    projects.value = await fetchClientProjects()
    if (projects.value.length > 0) {
      await selectProject(projects.value[0])
    }
  } finally {
    loadingProjects.value = false
    // Loading a project selects its first chat as well, which on a phone would
    // drop the client straight into the conversation with the list behind it.
    mobilePane.value = 'list'
  }
})

onUnmounted(() => {
  disconnectChatSocket()
})

// ── Project selection ──
async function selectProject(project: Project) {
  disconnectChatSocket()
  selectedProjectId.value = project.id
  selectedChatId.value = null
  messages.value = []
  
  await loadChats()
}

async function loadChats() {
  if (!selectedProjectId.value) return
  loadingChats.value = true
  try {
    chats.value = await fetchClientChats(selectedProjectId.value)
    if (chats.value.length > 0) {
      await selectChat(chats.value[0])
    } else {
      await createInitialChat()
    }
  } finally {
    loadingChats.value = false
  }
}

// A project without chats would leave the client staring at an empty screen, so
// give them a first chat automatically instead of making them create one.
async function createInitialChat() {
  if (!selectedProjectId.value) return
  try {
    const chat = await createClientChat(selectedProjectId.value, t('client.chat.default_name'))
    chats.value.unshift(chat)
    await selectChat(chat)
  } catch (e) {
    console.error('Failed to create initial chat', e)
  }
}

// ── Chat selection ──
// Tapping a chat in the list also opens it, which on a phone slides the list out
// of the way and on a wide screen changes nothing.
async function openChat(chat: Chat) {
  mobilePane.value = 'chat'
  await selectChat(chat)
}

async function selectChat(chat: Chat) {
  disconnectChatSocket()
  selectedChatId.value = chat.id
  messages.value = []
  agentLoopRunning.value = false
  agentLoopStopping.value = false
  typingUser.value = null
  await loadMessages()
  connectChatSocket()
  scrollToBottom()
}

// A chat opens on its newest page; older pages arrive as the reader scrolls up.
const MESSAGES_PAGE_SIZE = 10
const hasMoreMessages = ref(false)
const loadingOlderMessages = ref(false)

async function loadMessages() {
  const projectId = selectedProjectId.value
  const chatId = selectedChatId.value
  if (projectId == null || chatId == null) return
  loadingMessages.value = true
  hasMoreMessages.value = false
  try {
    const page = await fetchClientChatMessages(projectId, chatId, {
      limit: MESSAGES_PAGE_SIZE,
      includeDebug: false,
    })
    // The reader may have picked another chat while this was in flight.
    if (selectedChatId.value !== chatId) return
    messages.value = page.messages
    hasMoreMessages.value = page.has_more
    await nextTick()
    scrollToBottom()
  } finally {
    if (selectedChatId.value === chatId) loadingMessages.value = false
  }
}

// ── WebSocket ──
function connectChatSocket() {
  if (chatSocket && chatSocket.readyState === WebSocket.OPEN) return
  if (!selectedChatId.value) return
  const token = localStorage.getItem('token')
  if (!token) return
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${protocol}://${WS_BASE_URL}/ws/chats/${selectedChatId.value}?token=${encodeURIComponent(token)}`
  try {
    chatSocket = new WebSocket(url)
    chatSocket.onopen = () => { console.debug('WS connected') }
    chatSocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
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
      chatSocket = null
      if (selectedChatId.value) {
        setTimeout(connectChatSocket, 3000)
      }
    }
    chatSocket.onerror = () => {}
  } catch (e) {
    console.debug('WS not available, using HTTP')
  }
}

function disconnectChatSocket() {
  if (chatSocket) {
    try { chatSocket.close() } catch {}
    chatSocket = null
  }
}

// ── Send message ──
async function sendMessage() {
  if (agentLoopRunning.value) {
    stopAgentLoop()
    return
  }
  const content = newMessageContent.value.trim()
  if (!content || !selectedProjectId.value || !selectedChatId.value) return

  sending.value = true
  try {
    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
      agentLoopRunning.value = true
      chatSocket.send(JSON.stringify({ type: 'message', content }))
      newMessageContent.value = ''
    } else {
      // HTTP fallback
      await sendClientChatMessage(selectedProjectId.value, selectedChatId.value, {
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

// ── Create Chat ──
function openCreateChatModal() {
  newChatDescription.value = ''
  showCreateChatModal.value = true
}

function closeCreateChatModal() {
  showCreateChatModal.value = false
}

async function createChat() {
  if (!selectedProjectId.value || !newChatDescription.value.trim()) return
  try {
    const chat = await createClientChat(selectedProjectId.value, newChatDescription.value.trim())
    chats.value.unshift(chat)
    closeCreateChatModal()
    // A chat is created to be used, so open it instead of leaving the reader on
    // the list they started from.
    mobilePane.value = 'chat'
    await selectChat(chat)
  } catch (e) {
    console.error('Failed to create chat', e)
  }
}

// ── Edit Chat ──
function openEditChatModal() {
  if (!selectedChat.value) return
  editChatDescription.value = selectedChat.value.description || ''
  showEditChatModal.value = true
}

function closeEditChatModal() {
  showEditChatModal.value = false
}

async function saveChatEdit() {
  if (!selectedProjectId.value || !selectedChatId.value || !editChatDescription.value.trim()) return
  try {
    const updated = await updateClientChat(selectedProjectId.value, selectedChatId.value, {
      description: editChatDescription.value.trim(),
    })
    const idx = chats.value.findIndex(c => c.id === selectedChatId.value)
    if (idx >= 0) chats.value[idx] = updated
    closeEditChatModal()
  } catch (e) {
    console.error('Failed to update chat', e)
  }
}

// ── Delete Chat ──
async function deleteChat() {
  if (!selectedProjectId.value || !selectedChatId.value) return
  if (!confirm(t('client.chat.delete_confirm'))) return
  try {
    await deleteClientChat(selectedProjectId.value, selectedChatId.value)
    disconnectChatSocket()
    messages.value = []
    chats.value = chats.value.filter(c => c.id !== selectedChatId.value)
    selectedChatId.value = null
    // Nothing is open any more, so a phone has to fall back to the list.
    mobilePane.value = 'list'
    if (chats.value.length > 0) {
      await selectChat(chats.value[0])
    }
  } catch (e) {
    console.error('Failed to delete chat', e)
  }
}

// ── Helpers ──
function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

async function loadOlderMessages() {
  const projectId = selectedProjectId.value
  const chatId = selectedChatId.value
  const oldestId = messages.value[0]?.id
  if (loadingOlderMessages.value || !hasMoreMessages.value) return
  if (projectId == null || chatId == null || oldestId == null) return

  const container = messagesContainer.value
  // Prepending grows the scroller upwards. Remember where it was so the reader
  // keeps looking at the same bubble instead of being thrown to the new top.
  const previousHeight = container?.scrollHeight ?? 0
  const previousTop = container?.scrollTop ?? 0
  loadingOlderMessages.value = true
  try {
    const page = await fetchClientChatMessages(projectId, chatId, {
      limit: MESSAGES_PAGE_SIZE,
      beforeId: oldestId,
      includeDebug: false,
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
  const container = messagesContainer.value
  if (!container) return
  // Only the top edge pulls history in; everything else is ordinary scrolling.
  if (container.scrollTop <= 80) loadOlderMessages()
}

</script>

<style>
@keyframes spin { to { transform: rotate(360deg); } }

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
</style>

<style scoped>
.projects-layout {
  display: grid;
  /* Flexible minimums rather than one hard 800px floor: the columns narrow to
     meet the room they are given instead of pushing the conversation off the
     right edge on a tablet-sized window. */
  grid-template-columns: minmax(11rem, 14rem) minmax(11rem, 16rem) minmax(0, 1fr);
  gap: 1rem;
  align-items: stretch;
  width: 100%;
  min-width: 0;
  padding: 1rem;
  height: var(--shell-content-height);
}

.projects-layout-single {
  grid-template-columns: minmax(13rem, 16rem) minmax(0, 1fr);
}

.projects-col {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.projects-panel {
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  background: #fff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 1;
  min-height: 0;
}

.projects-panel-header {
  padding: 0.75rem;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  flex-shrink: 0;
}

.projects-panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.projects-panel-title {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
}

.projects-search-row {
  width: 100%;
}

.projects-search {
  width: 100%;
  padding: 0.375rem 0.625rem;
  border: 1px solid #d1d5db;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  outline: none;
  box-sizing: border-box;
  background: #fff;
  color: #111827;
}

.projects-search:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 2px #c7d2fe;
}

.projects-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-height: 6rem;
  position: relative;
}

.projects-item-wrapper {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.625rem;
  border: 1px solid transparent;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.1s ease;
}

.projects-item-wrapper:hover {
  background: #f9fafb;
}

.projects-item-selected {
  background: #eef2ff;
  border-color: #a5b4fc;
}

.projects-item-content {
  flex: 1;
  min-width: 0;
}

.projects-item-name {
  font-size: 0.8125rem;
  font-weight: 500;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.projects-item-meta {
  margin-top: 0.125rem;
}

.projects-item-desc {
  font-size: 0.75rem;
  color: #6b7280;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.projects-empty {
  padding: 2rem 1rem;
  text-align: center;
  font-size: 0.875rem;
  color: #9ca3af;
}

.projects-add-btn {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.25rem 0.625rem;
  border-radius: 0.375rem;
  border: 1px solid #a5b4fc;
  background: #eef2ff;
  color: #4f46e5;
  cursor: pointer;
  transition: all 0.1s;
  white-space: nowrap;
}

.projects-add-btn:hover {
  background: #e0e7ff;
}

.chat-card-wrapper {
  display: flex;
  align-items: center;
  padding: 0.5rem 0.625rem;
  border: 1px solid transparent;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.1s;
}

.chat-card-wrapper:hover {
  background: #f9fafb;
}

.chat-card-selected {
  background: #eef2ff;
  border-color: #a5b4fc;
}

.chat-card-top-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
}

.chat-card-avatar {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f3f4f6;
  border-radius: 50%;
  flex-shrink: 0;
  color: #6b7280;
}

.chat-card-info {
  flex: 1;
  min-width: 0;
}

.chat-card-name {
  font-size: 0.8125rem;
  font-weight: 500;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-card-actions {
  display: flex;
  gap: 0.125rem;
  flex-shrink: 0;
}

.chat-card-btn {
  width: 1.5rem;
  height: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  border-radius: 0.25rem;
}

.chat-card-btn:hover {
  color: #4f46e5;
  background: #eef2ff;
}

.chat-card-btn-danger:hover {
  color: #dc2626;
  background: #fef2f2;
}

.chat-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  flex: 1;
  min-height: 0;
}

.chat-header {
  flex-shrink: 0;
}

/* The chat name sits centred on its own until a phone needs the back button
   next to it (see the phone block at the end of this file). */
.chat-header-row {
  justify-content: center;
}

.chat-header-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Only the phone layout has a chat list to go back to. */
.chat-back-btn {
  display: none;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 1.75rem;
  height: 1.75rem;
  margin-left: -0.25rem;
  padding: 0;
  border: 0;
  border-radius: 0.375rem;
  background: transparent;
  color: #4b5563;
  cursor: pointer;
}

.chat-back-btn:hover {
  background: #f3f4f6;
}

.chat-back-btn svg {
  width: 1.125rem;
  height: 1.125rem;
}

.chat-messages {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 1rem 0.875rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  min-height: 0;
  /* Soft wash so the white cards and indigo bubbles sit on a surface. */
  background: linear-gradient(180deg, #f8fafc 0%, #f3f5fb 100%);
}
/* Sits above the first bubble while an older page is on its way in. */
.chat-load-older { display: flex; justify-content: center; padding: 0.25rem 0 0.5rem; }
.chat-load-older .loading-spinner { width: 1rem; height: 1rem; }

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

.chat-bubble-text {
  word-wrap: break-word;
  overflow-wrap: anywhere;
}

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
     message cannot push the rest of the conversation off screen. */
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
.chat-bubble-mine .markdown-content :deep(code) { background: rgba(255,255,255,0.18); }
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
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.875rem;
  color: #9ca3af;
}

.chat-date-divider { display: flex; justify-content: center; align-items: center; padding: 0.25rem 0 0.5rem; }

.chat-date-divider span {
  font-size: 0.6875rem; font-weight: 600; color: #6b7280;
  background: #eef2f7;
  padding: 0.15rem 0.6rem; border-radius: 9999px;
}

.chat-input-area {
  display: flex;
  gap: 0.5rem;
  padding: 0.75rem;
  border-top: 1px solid #e5e7eb;
  background: #fff;
  flex-shrink: 0;
}

.chat-input {
  flex: 1;
  padding: 0.5rem 0.625rem;
  border: 1px solid #d1d5db;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  outline: none;
  resize: none;
  background: #fff;
  color: #111827;
  font-family: inherit;
}

.chat-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 2px #c7d2fe;
}

.chat-send-btn {
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  background: #6366f1;
  color: #fff;
  border: none;
  cursor: pointer;
  white-space: nowrap;
}

.chat-send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.chat-send-btn:hover:not(:disabled) {
  background: #4f46e5;
}

.chat-stop-btn {
  background: #dc2626;
}

.chat-stop-btn:hover:not(:disabled) {
  background: #b91c1c;
}

.loading-spinner {
  width: 1.25rem;
  height: 1.25rem;
  border: 2px solid #e5e7eb;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  display: inline-block;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 0.75rem;
  padding: 1.25rem;
  width: 400px;
  max-width: 90vw;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
}

.modal h3 {
  margin: 0 0 1rem;
  font-size: 1rem;
  font-weight: 600;
  color: #1f2937;
}

.modal-body {
  margin-bottom: 1rem;
}

.modal-body label {
  display: block;
  font-size: 0.8rem;
  font-weight: 500;
  color: #374151;
  margin-bottom: 0.375rem;
}

.form-input {
  width: 100%;
  padding: 0.5rem 0.625rem;
  border: 1px solid #d1d5db;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  outline: none;
  box-sizing: border-box;
  background: #fff;
  color: #111827;
}

.form-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 2px #c7d2fe;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 0.375rem;
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  padding: 0.375rem 0.75rem;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #6366f1;
  color: white;
  border-color: #6366f1;
}

.btn-primary:hover:not(:disabled) {
  background: #4f46e5;
}

.btn-ghost {
  background: transparent;
  color: #6b7280;
  border-color: #d1d5db;
}

.btn-ghost:hover {
  background: #f9fafb;
  color: #111827;
  border-color: #9ca3af;
}

/* ── Phones ─────────────────────────────────────────────────── */
/*
 * Three columns side by side do not fit a phone: the panel used to keep its
 * 800px minimum width and scroll sideways, which left the conversation sliced
 * off at the right edge. Below the shell's breakpoint the panel collapses to a
 * single column and shows the chat list and the conversation one at a time,
 * with the back button in the chat header returning to the list.
 */
@media (max-width: 767px) {
  .projects-layout,
  .projects-layout-single {
    grid-template-columns: 1fr;
    gap: 0.75rem;
    min-width: 0;
    overflow-x: hidden;
    padding: 0.75rem;
  }

  /* A client with several projects keeps the picker above the chat list, but
     capped so the chats below still get most of the screen. */
  .projects-col-projects {
    max-height: 32%;
  }

  .mobile-pane-hidden {
    display: none;
  }

  .chat-header-row {
    justify-content: flex-start;
    gap: 0.5rem;
  }

  .chat-back-btn {
    display: flex;
  }

  /* A table needs the whole width of a phone, so a bubble holding one stops
     insetting itself and lets the table's own scroller do the work. */
  .chat-bubble:has(.md-table-wrap) {
    max-width: 100%;
  }
}
</style>
