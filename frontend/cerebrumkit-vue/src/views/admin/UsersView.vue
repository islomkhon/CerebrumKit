<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchAdminUsers, createUser, updateUser, deleteUser } from '../../api/users'
import type { User } from '../../types'

const { t } = useI18n()
const users = ref<User[]>([])
const loading = ref(true)
const error = ref('')

// ── Modal state ──
const showModal = ref(false)
const editingUser = ref<User | null>(null)
const saving = ref(false)
const modalError = ref('')

const form = ref({
  name: '',
  email: '',
  password: '',
  role: 'client',
  language: 'en',
})

// ── Delete confirm ──
const showDeleteConfirm = ref(false)
const deletingUser = ref<User | null>(null)
const deleting = ref(false)

// ── Load ──
async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    users.value = await fetchAdminUsers()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('admin.users.load_failed')
  } finally {
    loading.value = false
  }
}

// ── Open create modal ──
function openCreate() {
  editingUser.value = null
  form.value = { name: '', email: '', password: '', role: 'client', language: 'en' }
  modalError.value = ''
  showModal.value = true
}

// ── Open edit modal ──
function openEdit(user: User) {
  editingUser.value = user
  form.value = {
    name: user.name,
    email: user.email,
    password: '',
    role: user.role,
    language: user.language,
  }
  modalError.value = ''
  showModal.value = true
}

// ── Save (create or update) ──
async function handleSave() {
  // Validate
  if (!form.value.name.trim()) {
    modalError.value = t('admin.common.required_name')
    return
  }
  if (!form.value.email.trim()) {
    modalError.value = t('admin.users.required_email')
    return
  }
  if (!editingUser.value && !form.value.password) {
    modalError.value = t('admin.users.required_password')
    return
  }

  saving.value = true
  modalError.value = ''
  try {
    if (editingUser.value) {
      // Update — only send password if non-empty
      const payload: any = {
        name: form.value.name,
        email: form.value.email,
        role: form.value.role,
        language: form.value.language,
      }
      // Backend checks: if password is empty string it won't hash it
      payload.password = form.value.password || ''

      await updateUser(editingUser.value.id, payload)
    } else {
      await createUser({
        name: form.value.name,
        email: form.value.email,
        password: form.value.password,
        role: form.value.role,
        language: form.value.language,
      })
    }
    showModal.value = false
    await loadUsers()
  } catch (e: any) {
    modalError.value = e?.response?.data?.detail || t('admin.users.save_failed')
  } finally {
    saving.value = false
  }
}

// ── Delete ──
function confirmDelete(user: User) {
  deletingUser.value = user
  showDeleteConfirm.value = true
}

async function handleDelete() {
  if (!deletingUser.value) return
  deleting.value = true
  try {
    await deleteUser(deletingUser.value.id)
    showDeleteConfirm.value = false
    deletingUser.value = null
    await loadUsers()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('admin.users.delete_failed')
    showDeleteConfirm.value = false
  } finally {
    deleting.value = false
  }
}

function closeModal() {
  showModal.value = false
  editingUser.value = null
}

function closeDelete() {
  showDeleteConfirm.value = false
  deletingUser.value = null
}

onMounted(loadUsers)
</script>

<template>
  <div class="users-page">
    <!-- Header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('admin.users.title') }}</h1>
        <p class="page-subtitle">{{ t('admin.users.subtitle') }}</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        {{ t('admin.users.add') }}
      </button>
    </div>

    <!-- Error -->
    <div v-if="error" class="alert alert-error">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
      {{ error }}
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <span>{{ t('admin.users.loading') }}</span>
    </div>

    <!-- Table -->
    <div v-else class="card">
      <table class="users-table">
        <thead>
          <tr>
            <th>{{ t('admin.common.id') }}</th>
            <th>{{ t('admin.common.name') }}</th>
            <th>{{ t('admin.users.email') }}</th>
            <th>{{ t('admin.users.role') }}</th>
            <th>{{ t('admin.users.language') }}</th>
            <th>{{ t('admin.common.status') }}</th>
            <th class="th-actions">{{ t('admin.common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="users.length === 0">
            <td colspan="7" class="empty-row">{{ t('admin.users.empty') }}</td>
          </tr>
          <tr v-for="user in users" :key="user.id">
            <td class="td-id">{{ user.id }}</td>
            <td class="td-name">
              <div class="user-avatar-sm">{{ user.name.charAt(0).toUpperCase() }}</div>
              <span>{{ user.name }}</span>
            </td>
            <td class="td-email">{{ user.email }}</td>
            <td>
              <span class="badge" :class="user.role === 'admin' ? 'badge-admin' : 'badge-client'">
                {{ user.role }}
              </span>
            </td>
            <td class="td-lang">{{ user.language.toUpperCase() }}</td>
            <td>
              <span class="badge" :class="user.is_active ? 'badge-active' : 'badge-inactive'">
                {{ user.is_active ? t('admin.common.active') : t('admin.common.inactive') }}
              </span>
            </td>
            <td class="td-actions">
              <button class="btn-icon" :title="t('admin.common.edit')" @click="openEdit(user)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="btn-icon btn-icon-danger" :title="t('admin.common.delete')" @click="confirmDelete(user)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                </svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ── Create / Edit Modal ── -->
    <Teleport to="body">
      <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
        <div class="modal">
          <div class="modal-header">
            <h2>{{ editingUser ? t('admin.users.edit_title') : t('admin.users.create_title') }}</h2>
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
              <input v-model="form.name" type="text" class="form-input" placeholder="John Doe" />
            </div>

            <div class="form-group">
              <label>{{ t('admin.users.email') }}</label>
              <input v-model="form.email" type="email" class="form-input" placeholder="john@example.com" />
            </div>

            <div class="form-group">
              <label>
                {{ t('admin.users.password') }}
                <span v-if="editingUser" class="field-hint">{{ t('admin.users.password_hint') }}</span>
              </label>
              <input v-model="form.password" type="password" class="form-input" :placeholder="t('admin.users.password_placeholder')" />
            </div>

            <div class="form-row">
              <div class="form-group">
                <label>{{ t('admin.users.role') }}</label>
                <select v-model="form.role" class="form-input">
                  <option value="client">{{ t('admin.users.role_client') }}</option>
                  <option value="admin">{{ t('admin.users.role_admin') }}</option>
                </select>
              </div>
              <div class="form-group">
                <label>{{ t('admin.users.language') }}</label>
                <select v-model="form.language" class="form-input">
                  <option value="en">English</option>
                  <option value="ru">Русский</option>
                  <option value="zh">中文</option>
                  <option value="es">Español</option>
                  <option value="de">Deutsch</option>
                  <option value="fr">Français</option>
                </select>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button class="btn btn-ghost" @click="closeModal">{{ t('admin.common.cancel') }}</button>
            <button class="btn btn-primary" :disabled="saving" @click="handleSave">
              <div v-if="saving" class="spinner-sm"></div>
              {{ editingUser ? t('admin.users.save_changes') : t('admin.users.create_title') }}
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
            <h2>{{ t('admin.users.delete_title') }}</h2>
          </div>
          <div class="modal-body">
            <p>{{ t('admin.users.delete_confirm', { name: deletingUser?.name }) }}</p>
            <p class="text-muted">{{ t('admin.users.delete_warning') }}</p>
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
.users-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

/* ── Header ── */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 1.75rem;
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
}

/* ── Card / Table ── */
.card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
}
.users-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}
.users-table th {
  text-align: left;
  padding: 0.75rem 1rem;
  background: #f8fafc;
  color: #64748b;
  font-weight: 600;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid #e2e8f0;
}
.users-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #f1f5f9;
  color: #1e293b;
  vertical-align: middle;
}
.users-table tr:last-child td {
  border-bottom: none;
}
.users-table tr:hover {
  background: #f8fafc;
}
.th-actions { text-align: center; }
.td-id { color: #94a3b8; font-weight: 600; font-size: 0.8rem; width: 50px; }
.td-name {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
}
.user-avatar-sm {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.75rem;
  flex-shrink: 0;
}
.td-email { color: #475569; }
.td-lang { font-weight: 600; color: #64748b; }
.td-actions {
  text-align: center;
  white-space: nowrap;
}

/* ── Badges ── */
.badge {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: capitalize;
}
.badge-admin { background: #fef3c7; color: #b45309; }
.badge-client { background: #dbeafe; color: #1d4ed8; }
.badge-active { background: #dcfce7; color: #15803d; }
.badge-inactive { background: #f1f5f9; color: #64748b; }

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
.btn-primary {
  background: #6366f1;
  color: white;
}
.btn-primary:hover { background: #4f46e5; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost {
  background: transparent;
  color: #64748b;
  border: 1px solid #e2e8f0;
}
.btn-ghost:hover { background: #f8fafc; }
.btn-danger {
  background: #dc2626;
  color: white;
}
.btn-danger:hover { background: #b91c1c; }
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  transition: all 0.12s;
}
.btn-icon:hover { background: #f1f5f9; color: #1e293b; }
.btn-icon-danger:hover { background: #fef2f2; color: #dc2626; }

/* ── Alerts ── */
.alert {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 1rem;
  border-radius: 8px;
  font-size: 0.84rem;
  margin-bottom: 1rem;
}
.alert-error {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
}

/* ── Loading ── */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  padding: 3rem;
  color: #64748b;
  font-size: 0.9rem;
}
.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #e2e8f0;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.empty-row {
  text-align: center;
  color: #94a3b8;
  padding: 2.5rem 1rem !important;
  font-style: italic;
}

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
  max-width: 480px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.12);
  overflow: hidden;
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
.modal-body {
  padding: 1.25rem 1.5rem;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem 1.25rem;
}

/* ── Form ── */
.form-group {
  margin-bottom: 1rem;
}
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
select.form-input {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0.75rem center;
  padding-right: 2rem;
}

.text-muted {
  color: #64748b;
  font-size: 0.84rem;
  line-height: 1.5;
}

@media (max-width: 760px) {
  .users-page {
    /* The table's min-content width used to decide the page width, which the
       shell then clipped; capping it keeps the whole row on screen. */
    max-width: 100%;
    padding: 1.25rem 1rem;
  }
  .page-header {
    flex-direction: column;
    align-items: stretch;
    gap: 0.75rem;
    margin-bottom: 1.25rem;
  }

  /* Seven columns cannot fit a phone, so a row becomes a card: the avatar and
     name lead it, the email follows, and role, language and status share the
     footer line with the row actions in the corner. */
  .card {
    overflow: visible;
    background: transparent;
    border: 0;
  }
  .users-table,
  .users-table tbody,
  .users-table tr,
  .users-table td {
    display: block;
  }
  .users-table thead { display: none; }
  .users-table tr {
    position: relative;
    margin-bottom: 0.6rem;
    padding: 0.75rem 4.4rem 0.75rem 0.9rem;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    background: #fff;
  }
  .users-table tr:hover { background: #fff; }
  .users-table td {
    padding: 0;
    border: 0;
    color: #64748b;
    font-size: 0.82rem;
    line-height: 1.5;
  }
  .users-table .td-id { display: none; }
  .users-table .td-name {
    display: flex;
    align-items: center;
    margin-bottom: 0.2rem;
    font-size: 0.95rem;
  }
  .users-table .td-email { overflow-wrap: anywhere; }
  .users-table td:nth-child(4),
  .users-table td:nth-child(5),
  .users-table td:nth-child(6) {
    display: inline-block;
    margin-right: 0.5rem;
  }
  .users-table .td-actions {
    position: absolute;
    top: 0.6rem;
    right: 0.6rem;
    width: auto;
  }
  .users-table tr:has(.empty-row) { padding: 2rem 0.85rem; }
}
</style>
