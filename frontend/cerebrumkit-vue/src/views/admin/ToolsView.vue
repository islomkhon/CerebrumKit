<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { createTool, deleteTool, fetchTools, updateTool } from '../../api/agents'
import { generateJson } from '../../api/generator'
import type { Tool } from '../../types'
import './admin-crud.css'

const { t } = useI18n()
const tools = ref<Tool[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const showModal = ref(false)
const editingTool = ref<Tool | null>(null)
const saving = ref(false)
const generating = ref(false)
const modalError = ref('')
const form = ref({ name: '', description: '', type: '', body: '', is_active: true })
const generatorPrompt = ref('')
const generateDone = ref(false)
const descriptionEditor = ref<HTMLTextAreaElement | null>(null)
const bodyEditor = ref<HTMLTextAreaElement | null>(null)

const filteredTools = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return tools.value
  return tools.value.filter((tool) =>
    tool.name.toLowerCase().includes(q) ||
    (tool.description || '').toLowerCase().includes(q) ||
    (tool.type || '').toLowerCase().includes(q) ||
    (tool.body || '').toLowerCase().includes(q),
  )
})

async function loadTools() {
  loading.value = true
  error.value = ''
  try {
    tools.value = await fetchTools()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || t('admin.tools.load_failed')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingTool.value = null
  form.value = { name: '', description: '', type: '', body: '', is_active: true }
  generatorPrompt.value = ''
  generateDone.value = false
  modalError.value = ''
  showModal.value = true
}

function openEdit(tool: Tool) {
  editingTool.value = tool
  form.value = {
    name: tool.name,
    description: tool.description || '',
    type: tool.type || '',
    body: tool.body || '',
    is_active: tool.is_active,
  }
  generatorPrompt.value = ''
  generateDone.value = false
  modalError.value = ''
  showModal.value = true
}

async function generateToolFields() {
  generating.value = true
  generateDone.value = false
  modalError.value = ''
  const prompt = generatorPrompt.value.trim() + '. Based on this description, generate the fields for a tool definition form. Provide concise and clear values for each field. Use the following structure for your response:';
  const structure = { 
    name: form.value.name + '. The name should be concise, ideally one or two words. It should clearly indicate the tool\'s purpose.',
    description: form.value.description + '. The description is the deepseek tool definition JSON. No metter what the tool type is but the tool description should always be deepseek tool definition JSON. The tool definition schema is ' + JSON.stringify({
        "type": "type always 'function'",
        "function": {
            "name": "is the tool name shuold be same as the name field",
            "description": "A detailed description of what the tool does. It should provide enough information for the llm to understand the tool's functionality and how to use it.",
            "parameters": {
                "type": "type always 'object'",
                "properties": {
                    "parameter_name": {
                        "type": "parameter_type it can be object string, number, integer, boolean, array, enum, anyOf",
                        "description": "A description of the parameter. It should explain what the parameter is for and any important details about its usage. If the parameter type is enum, provide a list of possible values.",
                    }
                },
                "required": ["parameter names that are required for the function to work"],
            },
        }
    }),
    type: form.value.type + 'type is the tool type, it can be function or prompt',
    body: form.value.body + 'body is python code if type is function, or prompt if type is prompt. If the tool type is function, the body should be a valid Python function definition matching the name and parameters specified in the description JSON.function.parameters object. If the tool type is prompt, the body should be a text prompt that can be used by the system. If the tool searches or reads data from the database, use from app.core.database import get_db. get_db() returns a generator that yields a SQLAlchemy Session connected to the application database; use db = next(get_db()), query with that session, and close it in a finally block with db.close(). The body also runs with these server-supplied system variables already in scope, so never declare them as parameters and never expect the model to pass them: project_id (int, the id of the project the run belongs to), chat_id (int, the id of the chat the run belongs to), agent_id (int, the id of the agent that called the tool). Use them to scope the body to the run it belongs to, for example filtering rows by project_id instead of looking the project up by name.', 
  }
  try {
    const generated = await generateJson(prompt, structure)
    form.value = {
      name: typeof generated.name === 'string' ? generated.name : form.value.name,
      description: typeof generated.description === 'string' ? formatJsonText(generated.description) : form.value.description,
      type: typeof generated.type === 'string' ? generated.type : form.value.type,
      body: typeof generated.body === 'string' ? generated.body : form.value.body,
      is_active: true,
    }
    // The description has done its job: clear the field so it is ready for
    // the next tool, and confirm that something actually happened.
    generatorPrompt.value = ''
    generateDone.value = true
  } catch (err: any) {
    modalError.value = err?.response?.data?.detail || t('admin.tools.generate_failed')
  } finally {
    generating.value = false
  }
}

function formatJsonText(value: string) {
  const trimmed = value.trim()
  if (!trimmed) return value
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2)
  } catch {
    return value
  }
}

function formatDescriptionJson() {
  if (!form.value.description.trim()) return
  const formatted = formatJsonText(form.value.description)
  if (formatted === form.value.description) return
  form.value.description = formatted
  modalError.value = ''
}

function insertEditorIndent(field: 'description' | 'body', editor: HTMLTextAreaElement | null) {
  if (!editor) return
  const start = editor.selectionStart
  const end = editor.selectionEnd
  const value = form.value[field]
  form.value[field] = `${value.slice(0, start)}  ${value.slice(end)}`
  nextTick(() => {
    editor.focus()
    editor.setSelectionRange(start + 2, start + 2)
  })
}

async function saveTool() {
  if (!form.value.name.trim()) {
    modalError.value = t('admin.common.required_name')
    return
  }
  saving.value = true
  modalError.value = ''
  try {
    const payload = {
      name: form.value.name.trim(),
      description: form.value.description || null,
      type: form.value.type || null,
      body: form.value.body || null,
      is_active: form.value.is_active,
    }
    if (editingTool.value) await updateTool(editingTool.value.id, payload)
    else await createTool(payload)
    showModal.value = false
    await loadTools()
  } catch (err: any) {
    modalError.value = err?.response?.data?.detail || t('admin.tools.save_failed')
  } finally {
    saving.value = false
  }
}

async function removeTool(tool: Tool) {
  if (!window.confirm(t('admin.tools.delete_confirm', { name: tool.name }))) return
  try {
    await deleteTool(tool.id)
    await loadTools()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || t('admin.tools.delete_failed')
  }
}

onMounted(loadTools)
</script>

<template>
  <div class="admin-page">
    <div class="page-header">
      <div>
        <h1>{{ t('admin.tools.title') }}</h1>
        <p>{{ t('admin.tools.subtitle') }}</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">{{ t('admin.tools.add') }}</button>
    </div>

    <div v-if="error" class="alert">{{ error }}</div>

    <div class="toolbar">
      <input v-model="search" class="search" type="search" :placeholder="t('admin.tools.search')" />
    </div>

    <div class="card">
      <div v-if="loading" class="empty">{{ t('admin.tools.loading') }}</div>
      <table v-else class="admin-table">
        <colgroup>
          <col class="tools-col-id" />
          <col class="tools-col-name" />
          <col class="tools-col-description" />
          <col class="tools-col-type" />
          <col class="tools-col-body" />
          <col class="tools-col-status" />
          <col class="tools-col-actions" />
        </colgroup>
        <thead>
          <tr>
            <th>{{ t('admin.common.id') }}</th>
            <th>{{ t('admin.common.name') }}</th>
            <th>{{ t('admin.common.description') }}</th>
            <th>{{ t('admin.tools.type') }}</th>
            <th>{{ t('admin.tools.body') }}</th>
            <th>{{ t('admin.common.status') }}</th>
            <th class="actions-head">{{ t('admin.common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="filteredTools.length === 0">
            <td colspan="7" class="empty-cell">{{ t('admin.tools.empty') }}</td>
          </tr>
          <tr v-for="tool in filteredTools" :key="tool.id">
            <td class="id-cell">{{ tool.id }}</td>
            <td class="name-cell">{{ tool.name }}</td>
            <td class="muted clamp">{{ tool.description || '-' }}</td>
            <td class="muted">{{ tool.type || '-' }}</td>
            <td class="muted clamp">{{ tool.body || '-' }}</td>
            <td>
              <span class="badge" :class="tool.is_active ? 'active' : 'inactive'">
                {{ tool.is_active ? t('admin.common.active') : t('admin.common.inactive') }}
              </span>
            </td>
            <td class="actions-cell">
              <button class="icon-btn" :title="t('admin.common.edit')" @click="openEdit(tool)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="icon-btn danger" :title="t('admin.common.delete')" @click="removeTool(tool)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="3 6 5 6 21 6"/>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
                  <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                </svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <Teleport to="body">
      <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
        <div class="modal tool-modal">
          <header class="modal-header">
            <h2>{{ editingTool ? t('admin.tools.edit_title') : t('admin.tools.create_title') }}</h2>
          </header>
          <div class="modal-body tool-modal-body">
            <div v-if="modalError" class="alert">{{ modalError }}</div>
            <div class="tool-form-grid">
              <div class="tool-fields">
                <label class="field">
                  <span>{{ t('admin.common.name') }}</span>
                  <input v-model="form.name" class="input" type="text" />
                </label>
                <div class="field code-field">
                  <div class="field-title-row">
                    <span>{{ t('admin.common.description') }}</span>
                    <button class="mini-btn" type="button" @click="formatDescriptionJson">{{ t('admin.tools.format_json') }}</button>
                  </div>
                  <textarea
                    ref="descriptionEditor"
                    v-model="form.description"
                    class="input textarea code-editor tool-description-input"
                    spellcheck="false"
                    wrap="off"
                    placeholder='{"type":"function","function":{"name":"tool_name","description":"...","parameters":{"type":"object","properties":{},"required":[]}}}'
                    @keydown.tab.prevent="insertEditorIndent('description', descriptionEditor)"
                  ></textarea>
                </div>
                <label class="field">
                  <span>{{ t('admin.tools.type') }}</span>
                  <input v-model="form.type" class="input" type="text" :placeholder="t('admin.tools.type_placeholder')" />
                </label>
                <div class="field code-field">
                  <div class="field-title-row">
                    <span>{{ t('admin.tools.body') }}</span>
                  </div>
                  <textarea
                    ref="bodyEditor"
                    v-model="form.body"
                    class="input textarea code-editor tool-body-input"
                    spellcheck="false"
                    wrap="off"
                    placeholder="def tool_name(argument: str):&#10;    return argument"
                    @keydown.tab.prevent="insertEditorIndent('body', bodyEditor)"
                  ></textarea>
                </div>
                <label class="check-field">
                  <input v-model="form.is_active" type="checkbox" />
                  <span>{{ t('admin.common.active') }}</span>
                </label>
              </div>
              <label class="field generator-field">
                <span>{{ t('admin.tools.generate_from_description') }}</span>
                <textarea
                  v-model="generatorPrompt"
                  class="input generator-input"
                  :placeholder="t('admin.tools.generate_placeholder')"
                  @input="generateDone = false"
                ></textarea>
                <span v-if="generateDone" class="generator-done">{{ t('admin.tools.generate_done') }}</span>
              </label>
            </div>
          </div>
          <footer class="modal-footer">
            <button class="btn btn-ghost generate-btn" :disabled="generating || saving" @click="generateToolFields">
              <span v-if="generating" class="generate-spinner"></span>
              <span>{{ generating ? t('admin.common.generating') : t('admin.common.generate') }}</span>
            </button>
            <button class="btn btn-ghost" @click="showModal = false">{{ t('admin.common.cancel') }}</button>
            <button class="btn btn-primary" :disabled="saving" @click="saveTool">
              {{ saving ? t('admin.common.saving') : t('admin.common.save') }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.tools-col-id {
  width: 56px;
}

.tools-col-name {
  width: 28%;
}

.tools-col-description {
  width: 24%;
}

.tools-col-type {
  width: 96px;
}

.tools-col-body {
  width: 24%;
}

.tools-col-status {
  width: 96px;
}

.tools-col-actions {
  width: 104px;
}

.id-cell {
  width: 56px;
  padding-left: 0.75rem;
  padding-right: 0.5rem;
}

.name-cell {
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.25;
}

.tool-form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 0.7fr);
  gap: 1rem;
  align-items: stretch;
  min-height: 0;
}

.tool-modal {
  width: min(1040px, 100%);
  max-height: calc(100vh - 2rem);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tool-modal-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.tool-fields {
  display: grid;
  gap: 1rem;
  align-content: start;
}

.generator-input {
  line-height: 1.55;
  border-color: #d8dee8;
  background:
    linear-gradient(#ffffff, #ffffff) padding-box,
    linear-gradient(135deg, rgba(79, 70, 229, 0.14), rgba(14, 165, 233, 0.12)) border-box;
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.04);
}

.field-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.mini-btn {
  border: 1px solid #d8dee8;
  border-radius: 7px;
  background: #ffffff;
  color: #475569;
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1;
  padding: 0.42rem 0.58rem;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.mini-btn:hover {
  border-color: #9db0ca;
  background: #f8fafc;
  color: #0f172a;
}

.code-field {
  min-width: 0;
}

.code-editor {
  background: #0f172a;
  border-color: #273449;
  color: #dbeafe;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 0.86rem;
  line-height: 1.58;
  overflow: auto;
  resize: vertical;
  tab-size: 2;
  white-space: pre;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.04),
    inset 0 0 0 1px rgba(148, 163, 184, 0.08);
}

.code-editor:focus {
  border-color: #60a5fa;
  box-shadow:
    0 0 0 3px rgba(96, 165, 250, 0.18),
    inset 0 0 0 1px rgba(148, 163, 184, 0.08);
}

.code-editor::placeholder {
  color: #64748b;
}

.tool-description-input {
  min-height: 190px;
}

.tool-body-input {
  min-height: 230px;
}

.generator-field {
  min-height: 0;
  display: grid;
  grid-template-rows: auto 1fr auto;
  align-self: stretch;
}

.generator-done {
  margin-top: 0.4rem;
  color: #166534;
  font-size: 0.85rem;
  font-weight: 600;
}

.generator-input {
  height: 100%;
  min-height: 0;
  resize: vertical;
}

.generate-btn {
  min-width: 124px;
}

.generate-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 999px;
  animation: generate-spin 0.7s linear infinite;
}

@keyframes generate-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 760px) {
  .tool-form-grid {
    grid-template-columns: 1fr;
  }

  .generator-input {
    min-height: 140px;
  }
}

@media (max-width: 760px) {
  /* The card reads better with the type and the status together, so the body
     moves below them: every cell fills its own line except those two, and the
     body is ordered last. */
  .admin-table tr {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
  }
  .admin-table td { flex: 1 1 100%; }
  .admin-table td:nth-child(4),
  .admin-table td:nth-child(6) {
    flex: 0 0 auto;
    margin-right: 0.6rem;
  }
  .admin-table td:nth-child(5) { order: 1; }
}
</style>
