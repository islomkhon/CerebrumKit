<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  activatePlatform,
  createPlatform,
  deletePlatform,
  fetchPlatforms,
  testPlatform,
  updatePlatform,
} from '../../api/platforms'
import type { Platform } from '../../types'

const { t } = useI18n()

const platforms = ref<Platform[]>([])
const loading = ref(true)
const error = ref('')

/** The row the system is actually running on, fallback included. */
const effectivePlatform = computed(() => platforms.value.find(p => p.effective) ?? null)

type FormState = {
  name: string
  base_url: string
  api_key: string
  model: string
  temperature: string
  max_tokens: string
  thinking: boolean
  is_active: boolean
}

function emptyForm(): FormState {
  return {
    name: '',
    base_url: '',
    api_key: '',
    model: 'deepseek-chat',
    temperature: '',
    max_tokens: '',
    thinking: false,
    is_active: false,
  }
}

// ── Create / edit ──
const showModal = ref(false)
const editing = ref<Platform | null>(null)
const saving = ref(false)
const modalError = ref('')
const form = ref<FormState>(emptyForm())

// ── Per-row work ──
const activatingId = ref<number | null>(null)
const testingId = ref<number | null>(null)
const testResults = ref<Record<number, { ok: boolean; message: string }>>({})

// ── Delete ──
const showDeleteConfirm = ref(false)
const deletingPlatform = ref<Platform | null>(null)
const deleting = ref(false)

async function loadPlatforms() {
  loading.value = true
  error.value = ''
  try {
    platforms.value = await fetchPlatforms()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('admin.settings.load_failed')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  form.value = emptyForm()
  modalError.value = ''
  showModal.value = true
}

function openEdit(platform: Platform) {
  editing.value = platform
  form.value = {
    name: platform.name,
    base_url: platform.base_url ?? '',
    api_key: platform.api_key ?? '',
    model: platform.model,
    temperature: platform.temperature === null ? '' : String(platform.temperature),
    max_tokens: platform.max_tokens === null ? '' : String(platform.max_tokens),
    thinking: platform.thinking,
    is_active: platform.is_active,
  }
  modalError.value = ''
  showModal.value = true
}

/** Blank means "no opinion", which the backend stores as NULL. */
function parseOptionalNumber(raw: string): number | null | 'invalid' {
  const text = raw.trim()
  if (!text) return null
  const value = Number(text)
  return Number.isFinite(value) ? value : 'invalid'
}

async function handleSave() {
  if (!form.value.name.trim()) {
    modalError.value = t('admin.common.required_name')
    return
  }
  if (!form.value.model.trim()) {
    modalError.value = t('admin.settings.required_model')
    return
  }
  const temperature = parseOptionalNumber(form.value.temperature)
  if (temperature === 'invalid' || (temperature !== null && (temperature < 0 || temperature > 2))) {
    modalError.value = t('admin.settings.invalid_temperature')
    return
  }
  const maxTokens = parseOptionalNumber(form.value.max_tokens)
  if (maxTokens === 'invalid' || (maxTokens !== null && (!Number.isInteger(maxTokens) || maxTokens < 1))) {
    modalError.value = t('admin.settings.invalid_max_tokens')
    return
  }

  saving.value = true
  modalError.value = ''
  const payload = {
    name: form.value.name.trim(),
    base_url: form.value.base_url.trim() || null,
    api_key: form.value.api_key,
    model: form.value.model.trim(),
    temperature,
    max_tokens: maxTokens,
    thinking: form.value.thinking,
    is_active: form.value.is_active,
  }
  try {
    if (editing.value) {
      await updatePlatform(editing.value.id, payload)
    } else {
      await createPlatform(payload)
    }
    showModal.value = false
    await loadPlatforms()
  } catch (e: any) {
    modalError.value = e?.response?.data?.detail || t('admin.settings.save_failed')
  } finally {
    saving.value = false
  }
}

async function handleActivate(platform: Platform) {
  activatingId.value = platform.id
  error.value = ''
  try {
    await activatePlatform(platform.id)
    await loadPlatforms()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('admin.settings.activate_failed')
  } finally {
    activatingId.value = null
  }
}

async function handleTest(platform: Platform) {
  testingId.value = platform.id
  delete testResults.value[platform.id]
  try {
    testResults.value[platform.id] = await testPlatform(platform.id)
  } catch (e: any) {
    testResults.value[platform.id] = {
      ok: false,
      message: e?.response?.data?.detail || t('admin.settings.test_failed'),
    }
  } finally {
    testingId.value = null
  }
}

function confirmDelete(platform: Platform) {
  deletingPlatform.value = platform
  showDeleteConfirm.value = true
}

async function handleDelete() {
  if (!deletingPlatform.value) return
  deleting.value = true
  try {
    await deletePlatform(deletingPlatform.value.id)
    showDeleteConfirm.value = false
    deletingPlatform.value = null
    await loadPlatforms()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('admin.settings.delete_failed')
    showDeleteConfirm.value = false
  } finally {
    deleting.value = false
  }
}

function closeModal() {
  showModal.value = false
  editing.value = null
}

function closeDelete() {
  showDeleteConfirm.value = false
  deletingPlatform.value = null
}

onMounted(loadPlatforms)
</script>

<template>
  <div class="settings-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('admin.settings.title') }}</h1>
        <p class="page-subtitle">{{ t('admin.settings.subtitle') }}</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        {{ t('admin.settings.add') }}
      </button>
    </div>

    <div v-if="error" class="alert alert-error">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
      {{ error }}
    </div>

    <div v-if="effectivePlatform" class="effective-banner">
      <span class="effective-dot"></span>
      <span class="effective-label">{{ t('admin.settings.effective_now') }}</span>
      <strong>{{ effectivePlatform.name }}</strong>
      <code>{{ effectivePlatform.model }}</code>
    </div>
    <div v-else-if="!loading" class="alert alert-error">{{ t('admin.settings.effective_none') }}</div>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <span>{{ t('admin.common.loading') }}</span>
    </div>

    <div v-else-if="platforms.length === 0" class="card empty-card">
      {{ t('admin.settings.empty') }}
    </div>

    <div v-else class="platform-list">
      <article
        v-for="platform in platforms"
        :key="platform.id"
        class="platform-card"
        :class="{ 'is-effective': platform.effective }"
      >
        <header class="platform-head">
          <div class="platform-title">
            <h2>{{ platform.name }}</h2>
            <span v-if="platform.is_active" class="badge badge-active">{{ t('admin.common.active') }}</span>
            <span v-if="platform.effective" class="badge badge-effective">{{ t('admin.settings.effective') }}</span>
          </div>
          <div class="platform-actions">
            <button
              class="btn btn-ghost"
              :disabled="activatingId === platform.id || platform.is_active"
              @click="handleActivate(platform)"
            >
              {{ t('admin.settings.activate') }}
            </button>
            <button class="btn btn-ghost" :disabled="testingId === platform.id" @click="handleTest(platform)">
              {{ testingId === platform.id ? t('admin.settings.testing') : t('admin.settings.test') }}
            </button>
            <button class="btn btn-ghost" @click="openEdit(platform)">{{ t('admin.common.edit') }}</button>
            <button class="btn btn-ghost btn-ghost-danger" @click="confirmDelete(platform)">
              {{ t('admin.common.delete') }}
            </button>
          </div>
        </header>

        <div v-if="testResults[platform.id]" class="test-result" :class="{ ok: testResults[platform.id].ok }">
          <strong>{{ testResults[platform.id].ok ? t('admin.settings.test_ok') : t('admin.settings.test_fail') }}</strong>
          <span>{{ testResults[platform.id].message }}</span>
        </div>

        <dl class="platform-fields">
          <div>
            <dt>{{ t('admin.settings.model') }}</dt>
            <dd><code>{{ platform.model }}</code></dd>
          </div>
          <div>
            <dt>{{ t('admin.settings.base_url') }}</dt>
            <dd><code>{{ platform.base_url || t('admin.settings.use_default') }}</code></dd>
          </div>
          <div class="field-wide">
            <dt>{{ t('admin.settings.api_key') }}</dt>
            <dd><code class="secret">{{ platform.api_key || t('admin.settings.use_default') }}</code></dd>
          </div>
          <div>
            <dt>{{ t('admin.settings.temperature') }}</dt>
            <dd>{{ platform.temperature === null ? t('admin.settings.use_default') : platform.temperature }}</dd>
          </div>
          <div>
            <dt>{{ t('admin.settings.max_tokens') }}</dt>
            <dd>{{ platform.max_tokens === null ? t('admin.settings.no_limit') : platform.max_tokens }}</dd>
          </div>
          <div>
            <dt>{{ t('admin.settings.thinking') }}</dt>
            <dd>{{ platform.thinking ? t('admin.settings.on') : t('admin.settings.off') }}</dd>
          </div>
        </dl>
      </article>
    </div>

    <!-- ── Create / Edit Modal ── -->
    <Teleport to="body">
      <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
        <div class="modal">
          <div class="modal-header">
            <h2>{{ editing ? t('admin.settings.edit_title') : t('admin.settings.create_title') }}</h2>
            <button class="modal-close" @click="closeModal">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
          <div class="modal-body">
            <div v-if="modalError" class="alert alert-error">{{ modalError }}</div>

            <div class="form-group">
              <label>{{ t('admin.common.name') }}</label>
              <input v-model="form.name" class="form-input" :placeholder="t('admin.settings.name_placeholder')" />
            </div>

            <div class="form-group">
              <label>{{ t('admin.settings.base_url') }} <span class="field-hint">{{ t('admin.settings.base_url_hint') }}</span></label>
              <input v-model="form.base_url" class="form-input" :placeholder="t('admin.settings.url_placeholder')" />
            </div>

            <div class="form-group">
              <label>{{ t('admin.settings.api_key') }} <span class="field-hint">{{ t('admin.settings.api_key_hint') }}</span></label>
              <input v-model="form.api_key" class="form-input" :placeholder="t('admin.settings.key_placeholder')" />
            </div>

            <div class="form-group">
              <label>{{ t('admin.settings.model') }}</label>
              <input v-model="form.model" class="form-input" :placeholder="t('admin.settings.model_placeholder')" />
            </div>

            <div class="form-row">
              <div class="form-group">
                <label>{{ t('admin.settings.temperature') }} <span class="field-hint">{{ t('admin.settings.temperature_hint') }}</span></label>
                <input v-model="form.temperature" class="form-input" placeholder="0.7" />
              </div>
              <div class="form-group">
                <label>{{ t('admin.settings.max_tokens') }} <span class="field-hint">{{ t('admin.settings.max_tokens_hint') }}</span></label>
                <input v-model="form.max_tokens" class="form-input" placeholder="4096" />
              </div>
            </div>

            <label class="checkbox-row">
              <input v-model="form.thinking" type="checkbox" />
              <span>
                {{ t('admin.settings.thinking') }}
                <span class="field-hint">{{ t('admin.settings.thinking_hint') }}</span>
              </span>
            </label>

            <label class="checkbox-row">
              <input v-model="form.is_active" type="checkbox" />
              <span>
                {{ t('admin.settings.make_active') }}
                <span class="field-hint">{{ t('admin.settings.active_hint') }}</span>
              </span>
            </label>
          </div>
          <div class="modal-footer">
            <button class="btn btn-ghost" @click="closeModal">{{ t('admin.common.cancel') }}</button>
            <button class="btn btn-primary" :disabled="saving" @click="handleSave">
              <div v-if="saving" class="spinner-sm"></div>
              {{ saving ? t('admin.common.saving') : t('admin.common.save') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Delete Confirmation ── -->
    <Teleport to="body">
      <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="closeDelete">
        <div class="modal modal-sm">
          <div class="modal-header">
            <h2>{{ t('admin.settings.delete_title') }}</h2>
          </div>
          <div class="modal-body">
            <p>{{ t('admin.settings.delete_confirm', { name: deletingPlatform?.name }) }}</p>
            <p class="text-muted">{{ t('admin.settings.delete_warning') }}</p>
          </div>
          <div class="modal-footer">
            <button class="btn btn-ghost" @click="closeDelete">{{ t('admin.common.cancel') }}</button>
            <button class="btn btn-danger" :disabled="deleting" @click="handleDelete">
              <div v-if="deleting" class="spinner-sm"></div>
              {{ t('admin.common.delete') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.settings-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

/* ── Header ── */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 1.25rem;
  gap: 1rem;
}
.page-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0;
}
.page-subtitle {
  font-size: 0.88rem;
  color: #64748b;
  margin-top: 0.25rem;
  max-width: 60ch;
  line-height: 1.5;
}

/* ── Effective banner ── */
.effective-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  border-radius: 10px;
  padding: 0.7rem 0.9rem;
  margin-bottom: 1.25rem;
  font-size: 0.88rem;
  color: #3730a3;
}
.effective-label {
  color: #4f46e5;
  font-weight: 600;
}
.effective-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.2);
  flex-shrink: 0;
}

/* ── Cards ── */
.platform-list {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}
.card,
.platform-card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
}
.platform-card {
  padding: 1rem 1.15rem 1.1rem;
}
.platform-card.is-effective {
  border-color: #c7d2fe;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08);
}
.empty-card {
  padding: 2.5rem 1rem;
  text-align: center;
  color: #94a3b8;
  font-size: 0.9rem;
}
.platform-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}
.platform-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.platform-title h2 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: #0f172a;
}
.platform-actions {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}

/* ── Fields ── */
.platform-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 0.75rem 1.25rem;
  margin: 0.9rem 0 0;
}
.platform-fields .field-wide {
  grid-column: 1 / -1;
}
.platform-fields dt {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #94a3b8;
  margin-bottom: 0.15rem;
}
.platform-fields dd {
  margin: 0;
  font-size: 0.86rem;
  color: #1e293b;
  overflow-wrap: anywhere;
}
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.82rem;
  background: #f8fafc;
  border: 1px solid #eef2f7;
  border-radius: 5px;
  padding: 0.1rem 0.35rem;
}
code.secret {
  color: #334155;
}

/* ── Test result ── */
.test-result {
  margin-top: 0.85rem;
  padding: 0.55rem 0.75rem;
  border-radius: 8px;
  font-size: 0.84rem;
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
}
.test-result.ok {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #15803d;
}
.test-result span {
  overflow-wrap: anywhere;
}

/* ── Badges ── */
.badge {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 20px;
  font-size: 0.72rem;
  font-weight: 700;
}
.badge-active { background: #dcfce7; color: #15803d; }
.badge-effective { background: #e0e7ff; color: #4338ca; }

/* ── Buttons ── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-size: 0.88rem;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: all 0.12s;
}
.btn-primary { background: #6366f1; color: white; }
.btn-primary:hover { background: #4f46e5; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost {
  background: transparent;
  color: #64748b;
  border: 1px solid #e2e8f0;
}
.btn-ghost:hover { background: #f8fafc; }
.btn-ghost:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-ghost-danger { color: #b91c1c; }
.btn-ghost-danger:hover { background: #fef2f2; border-color: #fecaca; }
.btn-danger { background: #dc2626; color: white; }
.btn-danger:hover { background: #b91c1c; }
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Alerts ── */
.alert {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 0.85rem;
  border-radius: 8px;
  font-size: 0.86rem;
  margin-bottom: 1rem;
}
.alert-error { background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c; }

/* ── Loading ── */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  padding: 3rem 1rem;
  color: #94a3b8;
  font-size: 0.88rem;
}
.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid #e2e8f0;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
.spinner-sm {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(255, 255, 255, 0.45);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Modal ── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}
.modal {
  background: white;
  border-radius: 14px;
  width: 100%;
  max-width: 520px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,0.12);
}
.modal-sm { max-width: 400px; }
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem 0;
}
.modal-header h2 {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
  color: #0f172a;
}
.modal-close {
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
}
.modal-close:hover { background: #f1f5f9; color: #475569; }
.modal-body { padding: 1.25rem 1.5rem; }
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem 1.25rem;
}

/* ── Form ── */
.form-group { margin-bottom: 1rem; }
.form-group label {
  display: block;
  font-size: 0.82rem;
  font-weight: 600;
  color: #334155;
  margin-bottom: 0.35rem;
}
.field-hint {
  font-weight: 400;
  color: #94a3b8;
  font-size: 0.78rem;
}
.form-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.88rem;
  color: #1e293b;
  background: white;
  transition: border-color 0.12s;
  box-sizing: border-box;
}
.form-input:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99,102,241,0.1);
}
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}
.checkbox-row {
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  margin-top: 0.75rem;
  font-size: 0.86rem;
  color: #334155;
  cursor: pointer;
}
.checkbox-row input { margin-top: 0.15rem; }

.text-muted {
  color: #64748b;
  font-size: 0.84rem;
  line-height: 1.5;
}

@media (max-width: 760px) {
  .settings-page {
    max-width: 100%;
    padding: 1.25rem 1rem;
  }
  .page-header {
    flex-direction: column;
    align-items: stretch;
    gap: 0.75rem;
  }
  .platform-actions { width: 100%; }
  .form-row { grid-template-columns: 1fr; }
}
</style>
