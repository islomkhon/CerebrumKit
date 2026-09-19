<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { createSkill, deleteSkill, fetchSkills, fetchTools, updateSkill } from '../../api/agents'
import { generateJson } from '../../api/generator'
import type { Skill, Tool } from '../../types'
import './admin-crud.css'

const { t } = useI18n()
const skills = ref<Skill[]>([])
const tools = ref<Tool[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const showModal = ref(false)
const editingSkill = ref<Skill | null>(null)
const saving = ref(false)
const generating = ref(false)
const modalError = ref('')
const form = ref({ name: '', description: '', tool_ids: [] as number[], is_active: true })
const generatorPrompt = ref('')

const filteredSkills = computed(() => {
  const q = search.value.trim().toLowerCase()
  return skills.value.filter((skill) => {
    return !q ||
      skill.name.toLowerCase().includes(q) ||
      (skill.description || '').toLowerCase().includes(q) ||
      toolNames(skill.tool_ids).toLowerCase().includes(q)
  })
})

const selectedTools = computed(() => {
  const selectedIds = new Set(form.value.tool_ids)
  return activeTools.value.filter((tool) => selectedIds.has(tool.id))
})

const activeTools = computed(() => tools.value.filter((tool) => tool.is_active))

function toolNames(toolIds: number[] = []) {
  if (toolIds.length === 0) return ''
  const names = new Map(tools.value.map((tool) => [tool.id, tool.name]))
  return toolIds.map((id) => names.get(id)).filter(Boolean).join(', ')
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const [skillRows, toolRows] = await Promise.all([fetchSkills(), fetchTools()])
    skills.value = skillRows
    tools.value = toolRows
  } catch (err: any) {
    error.value = err?.response?.data?.detail || t('admin.skills.load_failed')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingSkill.value = null
  form.value = { name: '', description: '', tool_ids: [], is_active: true }
  generatorPrompt.value = ''
  modalError.value = ''
  showModal.value = true
}

function openEdit(skill: Skill) {
  editingSkill.value = skill
  const activeToolIds = new Set(activeTools.value.map((tool) => tool.id))
  form.value = {
    name: skill.name,
    description: skill.description || '',
    tool_ids: [...(skill.tool_ids || [])].filter((toolId) => activeToolIds.has(toolId)),
    is_active: skill.is_active,
  }
  generatorPrompt.value = ''
  modalError.value = ''
  showModal.value = true
}

function toggleTool(toolId: number, checked: boolean) {
  const current = new Set(form.value.tool_ids)
  if (checked) current.add(toolId)
  else current.delete(toolId)
  form.value.tool_ids = [...current]
}

function selectedToolContext() {
  return selectedTools.value.map((tool) => {
    return [
      `Tool: ${tool.name}`,
      `Type: ${tool.type || 'Tool'}`,
      `Description: ${tool.description || 'No description provided.'}`,
      `Body: ${tool.body || 'No body provided.'}`,
    ].join('\n')
  }).join('\n\n---\n\n')
}

async function generateStkillFields() {
  if (form.value.tool_ids.length === 0) {
    modalError.value = t('admin.skills.select_tool_first')
    return
  }
  generating.value = true
  modalError.value = ''
  const prompt = [
    generatorPrompt.value.trim(),
    'Based on this description and the assigned tools, generate fields for a skill form.',
    'The skill description must be markdown that can be used as the beginning of a common SKILL.md file.',
    'Use the assigned tool descriptions and bodies as the technical context for what the skill can do.',
    '',
    'Assigned tool context:',
    selectedToolContext(),
    '',
    'Use the following structure for your response:',
  ].join('\n')
  const structure = {
    name: form.value.name + '. The name should be concise and describe the skill capability.',
    description: form.value.description + '. Generate markdown for the start of a SKILL.md file. Include a clear title, purpose, when to use this skill, and concise instructions that reference the assigned tools without inventing unavailable tools.',
  }
  try {
    const generated = await generateJson(prompt, structure)
    form.value = {
      ...form.value,
      name: typeof generated.name === 'string' ? generated.name : form.value.name,
      description: typeof generated.description === 'string' ? generated.description : form.value.description,
    }
  } catch (err: any) {
    modalError.value = err?.response?.data?.detail || t('admin.skills.generate_failed')
  } finally {
    generating.value = false
  }
}

async function saveSkill() {
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
      tool_ids: form.value.tool_ids,
      is_active: form.value.is_active,
    }
    if (editingSkill.value) await updateSkill(editingSkill.value.id, payload)
    else await createSkill(payload)
    showModal.value = false
    await loadData()
  } catch (err: any) {
    modalError.value = err?.response?.data?.detail || t('admin.skills.save_failed')
  } finally {
    saving.value = false
  }
}

async function removeSkill(skill: Skill) {
  if (!window.confirm(t('admin.skills.delete_confirm', { name: skill.name }))) return
  try {
    await deleteSkill(skill.id)
    await loadData()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || t('admin.skills.delete_failed')
  }
}

onMounted(loadData)
</script>

<template>
  <div class="admin-page">
    <div class="page-header">
      <div>
        <h1>{{ t('admin.skills.title') }}</h1>
        <p>{{ t('admin.skills.subtitle') }}</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">{{ t('admin.skills.add') }}</button>
    </div>

    <div v-if="error" class="alert">{{ error }}</div>

    <div class="toolbar">
      <input v-model="search" class="search" type="search" :placeholder="t('admin.skills.search')" />
    </div>

    <div class="card">
      <div v-if="loading" class="empty">{{ t('admin.skills.loading') }}</div>
      <table v-else class="admin-table">
        <colgroup>
          <col class="skills-col-id" />
          <col class="skills-col-name" />
          <col class="skills-col-description" />
          <col class="skills-col-tools" />
          <col class="skills-col-status" />
          <col class="skills-col-actions" />
        </colgroup>
        <thead>
          <tr>
            <th>{{ t('admin.common.id') }}</th>
            <th>{{ t('admin.common.name') }}</th>
            <th>{{ t('admin.common.description') }}</th>
            <th>{{ t('admin.skills.tools') }}</th>
            <th>{{ t('admin.common.status') }}</th>
            <th class="actions-head">{{ t('admin.common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="filteredSkills.length === 0">
            <td colspan="6" class="empty-cell">{{ t('admin.skills.empty') }}</td>
          </tr>
          <tr v-for="skill in filteredSkills" :key="skill.id">
            <td class="id-cell">{{ skill.id }}</td>
            <td class="name-cell">{{ skill.name }}</td>
            <td class="muted clamp">{{ skill.description || '-' }}</td>
            <td class="muted clamp">{{ toolNames(skill.tool_ids) || '-' }}</td>
            <td>
              <span class="badge" :class="skill.is_active ? 'active' : 'inactive'">
                {{ skill.is_active ? t('admin.common.active') : t('admin.common.inactive') }}
              </span>
            </td>
            <td class="actions-cell">
              <button class="icon-btn" :title="t('admin.common.edit')" @click="openEdit(skill)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="icon-btn danger" :title="t('admin.common.delete')" @click="removeSkill(skill)">
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
        <div class="modal skill-modal">
          <header class="modal-header">
            <h2>{{ editingSkill ? t('admin.skills.edit_title') : t('admin.skills.create_title') }}</h2>
          </header>
          <div class="modal-body skill-modal-body">
            <div v-if="modalError" class="alert">{{ modalError }}</div>
            <div class="skill-form-grid" :class="{ 'has-generator': form.tool_ids.length > 0 }">
              <div class="skill-fields">
                <label class="field">
                  <span>{{ t('admin.common.name') }}</span>
                  <input v-model="form.name" class="input" type="text" />
                </label>
                <label class="field">
                  <span>{{ t('admin.common.description') }}</span>
                  <textarea
                    v-model="form.description"
                    class="input textarea skill-description-input"
                    spellcheck="false"
                    placeholder="# Skill name&#10;&#10;## Purpose&#10;..."
                  ></textarea>
                </label>
                <div class="field">
                  <span>{{ t('admin.skills.tools') }}</span>
                  <div class="tool-picker">
                    <label v-if="activeTools.length === 0" class="tool-option muted">
                      {{ t('admin.skills.no_active_tools') }}
                    </label>
                    <label v-for="tool in activeTools" :key="tool.id" class="tool-option">
                      <input
                        type="checkbox"
                        :checked="form.tool_ids.includes(tool.id)"
                        @change="toggleTool(tool.id, ($event.target as HTMLInputElement).checked)"
                      />
                      <span class="tool-option-main">
                        <span>{{ tool.name }}</span>
                        <small>{{ tool.type || 'Tool' }}</small>
                      </span>
                    </label>
                  </div>
                </div>
                <label class="check-field">
                  <input v-model="form.is_active" type="checkbox" />
                  <span>{{ t('admin.common.active') }}</span>
                </label>
              </div>
              <label v-if="form.tool_ids.length > 0" class="field generator-field">
                <span>{{ t('admin.skills.generate_from_tools') }}</span>
                <textarea
                  v-model="generatorPrompt"
                  class="input generator-input"
                  :placeholder="t('admin.skills.generate_placeholder')"
                ></textarea>
              </label>
            </div>
          </div>
          <footer class="modal-footer">
            <button
              v-if="form.tool_ids.length > 0"
              class="btn btn-ghost generate-btn"
              :disabled="generating || saving"
              @click="generateStkillFields"
            >
              <span v-if="generating" class="generate-spinner"></span>
              <span>{{ generating ? t('admin.common.generating') : t('admin.common.generate') }}</span>
            </button>
            <button class="btn btn-ghost" @click="showModal = false">{{ t('admin.common.cancel') }}</button>
            <button class="btn btn-primary" :disabled="saving" @click="saveSkill">
              {{ saving ? t('admin.common.saving') : t('admin.common.save') }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.skills-col-id {
  width: 56px;
}

.skills-col-name {
  width: 30%;
}

.skills-col-description {
  width: 28%;
}

.skills-col-tools {
  width: 26%;
}

.skills-col-status {
  width: 96px;
}

.skills-col-actions {
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

.skill-modal {
  width: min(960px, 100%);
  max-height: calc(100vh - 2rem);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.skill-modal-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.skill-form-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
  min-height: 0;
}

.skill-form-grid.has-generator {
  grid-template-columns: minmax(0, 1fr) minmax(220px, 0.7fr);
  align-items: stretch;
}

.skill-fields {
  display: grid;
  gap: 1rem;
  align-content: start;
  min-width: 0;
}

.skill-description-input {
  min-height: 220px;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 0.86rem;
  line-height: 1.58;
  tab-size: 2;
}

.tool-picker {
  max-height: 220px;
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.tool-option {
  min-height: 46px;
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid #e2e8f0;
  color: #334155;
  cursor: pointer;
}

.tool-option:last-child {
  border-bottom: 0;
}

.tool-option:hover {
  background: #f8fafc;
}

.tool-option input {
  flex: 0 0 auto;
}

.tool-option-main {
  min-width: 0;
  display: grid;
  gap: 0.15rem;
}

.tool-option-main span {
  overflow: hidden;
  color: #0f172a;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-option-main small {
  color: #64748b;
  font-size: 0.76rem;
  font-weight: 650;
}

.generator-field {
  min-height: 0;
  display: grid;
  grid-template-rows: auto 1fr;
  align-self: stretch;
}

.generator-input {
  height: 100%;
  min-height: 0;
  resize: vertical;
  line-height: 1.55;
  border-color: #d8dee8;
  background:
    linear-gradient(#ffffff, #ffffff) padding-box,
    linear-gradient(135deg, rgba(79, 70, 229, 0.14), rgba(14, 165, 233, 0.12)) border-box;
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.04);
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
  .skill-form-grid.has-generator {
    grid-template-columns: 1fr;
  }

  .generator-input {
    min-height: 140px;
  }
}

</style>
