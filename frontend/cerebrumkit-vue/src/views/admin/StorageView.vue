<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  createRow,
  createTable,
  deleteRow,
  deleteTable,
  exportExcel,
  fetchRows,
  fetchAllTables,
  importExcel,
  previewExcel,
  updateRow,
  updateTable,
} from '../../api/storage'
import type { ExcelPreview } from '../../api/storage'
import type { StorageColumnInfo, StorageRow, StorageTableCreate, StorageTableInfo } from '../../types'

const { t } = useI18n()

const dataTypes = [
  'integer', 'bigInteger', 'smallInteger', 'tinyInteger',
  'string', 'text', 'longText', 'mediumText',
  'boolean', 'float', 'double', 'decimal',
  'date', 'dateTime', 'time', 'timestamp',
  'json', 'jsonb',
]

type ModalColumn = {
  name: string
  data_type: string
  description: string
  length: number | null
  nullable: boolean
  default_value: any
}

const tables = ref<StorageTableInfo[]>([])
const rows = ref<StorageRow[]>([])
const rowPerPage = ref<number | 'all'>(50)
const rowPage = ref(1)
const sortBy = ref('id')
const sortDir = ref<'asc' | 'desc'>('asc')
const rowTotal = ref(0)
const rowPages = ref(1)
const selectedTableName = ref<string | null>(null)
const tableSearch = ref('')
const rowSearch = ref('')
const loadingTables = ref(false)
const loadingRows = ref(false)
const selectedRowIds = ref<number[]>([])
const pageError = ref('')
const notice = ref('')

const showTableModal = ref(false)
const editingTableName = ref<string | null>(null)
const tableName = ref('')
const tableDescription = ref('')
const modalColumns = ref<ModalColumn[]>([])
const tableSaving = ref(false)
const tableError = ref('')

const showRowModal = ref(false)
const editingRowId = ref<number | null>(null)
const rowData = ref<Record<string, any>>({})
const rowSaving = ref(false)
const rowError = ref('')

const showImportModal = ref(false)
const excelFile = ref<File | null>(null)
const excelPreview = ref<ExcelPreview | null>(null)
const importMapping = ref<Record<string, string>>({})
const previewingExcel = ref(false)
const importing = ref(false)

const filteredTables = computed(() => {
  const q = tableSearch.value.trim().toLowerCase()
  const list = q
    ? tables.value.filter((table) => table.name.toLowerCase().includes(q))
    : [...tables.value]
  return list.sort(
    (a, b) => Number(Boolean(a.is_system)) - Number(Boolean(b.is_system)) || a.name.localeCompare(b.name),
  )
})

const selectedTable = computed(() => tables.value.find((table) => table.name === selectedTableName.value) || null)

// Phones show one pane at a time - the table list, then the rows of the table
// that was tapped - because the two panes side by side need ~860px. The
// loaders still pick the first table on their own; those calls pass `auto` so
// a phone stays on the list until the user picks one.
const mobilePane = ref<'tables' | 'data'>('tables')

const schemaColumns = computed<StorageColumnInfo[]>(() =>
  (selectedTable.value?.columns || []).filter(
    (column) => !['id', 'created_at', 'updated_at'].includes(column.name),
  ),
)

function showNotice(message: string) {
  notice.value = message
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 2400)
}

function errorMessage(error: any, fallback: string) {
  return error?.response?.data?.detail || error?.message || fallback
}

async function loadAllTables() {
  loadingTables.value = true
  pageError.value = ''
  try {
    tables.value = await fetchAllTables()
    if (!selectedTableName.value && tables.value.length) {
      await selectTable(tables.value[0].name, { auto: true })
    }
  } catch (error: any) {
    pageError.value = errorMessage(error, t('admin.storage.failed_load_tables'))
  } finally {
    loadingTables.value = false
  }
}

async function selectTable(tableName: string, opts: { auto?: boolean } = {}) {
  if (!opts.auto) mobilePane.value = 'data'
  selectedTableName.value = tableName
  selectedRowIds.value = []
  rowPage.value = 1
  await loadRows()
}

async function loadRows() {
  if (!selectedTableName.value) return
  loadingRows.value = true
  pageError.value = ''
  try {
    const data = await fetchRows(selectedTableName.value, rowSearch.value, rowPage.value, rowPerPage.value, sortBy.value, sortDir.value)
    rows.value = data.items
    rowTotal.value = data.total
    rowPages.value = data.pages
    rowPage.value = data.page
  } catch (error: any) {
    pageError.value = errorMessage(error, t('admin.storage.failed_load_rows'))
  } finally {
    loadingRows.value = false
  }
}

function toggleSort(column: string) {
  if (sortBy.value === column) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = column
    sortDir.value = 'asc'
  }
  rowPage.value = 1
  loadRows()
}

function sortArrowPath(): string {
  return sortDir.value === 'desc' ? 'M5 9l7 7 7-7' : 'M5 15l7-7 7 7'
}

function prevPage() {
  if (rowPage.value > 1) {
    rowPage.value -= 1
    loadRows()
  }
}

function nextPage() {
  if (rowPage.value < rowPages.value) {
    rowPage.value += 1
    loadRows()
  }
}

function onRowPerPageChange() {
  rowPage.value = 1
  loadRows()
}

function openCreateTable() {
  editingTableName.value = null
  tableName.value = ''
  tableDescription.value = ''
  modalColumns.value = []
  tableError.value = ''
  showTableModal.value = true
}

function openEditTable(table: StorageTableInfo) {
  editingTableName.value = table.name
  tableName.value = table.name
  tableDescription.value = table.description || ''
  modalColumns.value = (table.columns || [])
    .filter((column) => !['id', 'created_at', 'updated_at'].includes(column.name))
    .map((column) => ({
      name: column.name,
      data_type: column.editor_type || 'string',
      description: column.description || '',
      length: column.length ?? null,
      nullable: column.nullable ?? true,
      default_value: column.default_value ?? null,
    }))
  tableError.value = ''
  showTableModal.value = true
}

function addColumn() {
  modalColumns.value.push({
    name: '',
    data_type: 'string',
    description: '',
    length: 255,
    nullable: true,
    default_value: null,
  })
}

function removeColumn(index: number) {
  modalColumns.value.splice(index, 1)
}

async function saveTable() {
  if (!tableName.value.trim()) {
    tableError.value = t('admin.storage.table_name_required')
    return
  }
  tableSaving.value = true
  tableError.value = ''
  try {
    const payload: StorageTableCreate = {
      name: tableName.value,
      description: tableDescription.value,
      columns: modalColumns.value.map((column) => ({
        name: column.name,
        data_type: column.data_type,
        description: column.description,
        length: column.length,
        nullable: column.nullable,
        default_value: column.default_value === '' ? null : column.default_value,
      })),
    }
    if (editingTableName.value) {
      await updateTable(editingTableName.value, payload)
    } else {
      await createTable(payload)
    }
    showTableModal.value = false
    await loadAllTables()
    if (selectedTableName.value && !tables.value.some((table) => table.name === selectedTableName.value)) {
      selectedTableName.value = null
    }
    if (selectedTableName.value) {
      await loadRows()
    } else if (tables.value.length) {
      await selectTable(tables.value[0].name, { auto: true })
    }
    showNotice(t('admin.storage.table_saved'))
  } catch (error: any) {
    tableError.value = errorMessage(error, t('admin.storage.failed_save_table'))
  } finally {
    tableSaving.value = false
  }
}

async function removeTable(table: StorageTableInfo) {
  if (!window.confirm(t('admin.storage.delete_table_confirm', { name: table.name }))) return
  try {
    await deleteTable(table.name)
    if (selectedTableName.value === table.name) {
      selectedTableName.value = null
      rows.value = []
    }
    await loadAllTables()
    showNotice(t('admin.storage.table_deleted'))
  } catch (error: any) {
    pageError.value = errorMessage(error, t('admin.storage.failed_delete_table'))
  }
}

function openCreateRow() {
  editingRowId.value = null
  rowData.value = Object.fromEntries(schemaColumns.value.map((column) => [column.name, '']))
  rowError.value = ''
  showRowModal.value = true
}

function openEditRow(row: StorageRow) {
  editingRowId.value = row.id
  rowData.value = Object.fromEntries(
    schemaColumns.value.map((column) => [column.name, toFormValue(row.data[column.name], column)]),
  )
  rowError.value = ''
  showRowModal.value = true
}

async function saveRow() {
  if (!selectedTableName.value) return
  rowSaving.value = true
  rowError.value = ''
  try {
    const payload = Object.fromEntries(
      schemaColumns.value.map((column) => [column.name, fromFormValue(rowData.value[column.name], column)]),
    )
    if (editingRowId.value) {
      await updateRow(selectedTableName.value, editingRowId.value, payload)
    } else {
      await createRow(selectedTableName.value, payload)
    }
    showRowModal.value = false
    await loadRows()
    showNotice(t('admin.storage.row_saved'))
  } catch (error: any) {
    rowError.value = errorMessage(error, t('admin.storage.failed_save_row'))
  } finally {
    rowSaving.value = false
  }
}

async function removeRow(row: StorageRow) {
  if (!selectedTableName.value) return
  if (!window.confirm(t('admin.storage.delete_row_confirm', { id: row.id }))) return
  try {
    await deleteRow(selectedTableName.value, row.id)
    if (rows.value.length === 1 && rowPage.value > 1) {
      rowPage.value -= 1
    }
    await loadRows()
    showNotice(t('admin.storage.row_deleted'))
  } catch (error: any) {
    pageError.value = errorMessage(error, t('admin.storage.failed_delete_row'))
  }
}

const allRowsSelected = computed(() =>
  rows.value.length > 0 && selectedRowIds.value.length === rows.value.length,
)

function toggleRow(rowId: number) {
  const index = selectedRowIds.value.indexOf(rowId)
  if (index >= 0) selectedRowIds.value.splice(index, 1)
  else selectedRowIds.value.push(rowId)
}

function toggleAllRows() {
  if (allRowsSelected.value) selectedRowIds.value = []
  else selectedRowIds.value = rows.value.map((row) => row.id)
}

async function bulkDeleteRows() {
  if (!selectedTableName.value || selectedRowIds.value.length === 0) return
  const count = selectedRowIds.value.length
  if (!window.confirm(t('admin.storage.delete_selected_confirm', { count }))) return
  try {
    for (const rowId of [...selectedRowIds.value]) {
      await deleteRow(selectedTableName.value, rowId)
    }
    const removed = count
    selectedRowIds.value = []
    if (rows.value.length === removed && rowPage.value > 1) {
      rowPage.value -= 1
    }
    await loadRows()
    showNotice(t('admin.storage.rows_deleted', { count: removed }))
  } catch (error: any) {
    pageError.value = errorMessage(error, t('admin.storage.failed_delete_row'))
  }
}

async function handleExport() {
  if (!selectedTableName.value || !selectedTable.value) return
  try {
    const blob = await exportExcel(selectedTableName.value)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${selectedTable.value.name}.xlsx`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error: any) {
    pageError.value = errorMessage(error, t('admin.storage.failed_export'))
  }
}

async function handleImport() {
  if (!selectedTableName.value || !excelFile.value) return
  const mapping = Object.fromEntries(
    Object.entries(importMapping.value).filter(([, excelColumn]) => Boolean(excelColumn)),
  )
  importing.value = true
  try {
    const result = await importExcel(selectedTableName.value, excelFile.value, mapping)
    showImportModal.value = false
    resetImportState()
    await loadRows()
    showNotice(t('admin.storage.imported_rows', { count: result.imported }))
  } catch (error: any) {
    pageError.value = errorMessage(error, t('admin.storage.failed_import'))
  } finally {
    importing.value = false
  }
}

async function onExcelFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  excelFile.value = input.files?.[0] || null
  excelPreview.value = null
  importMapping.value = {}
  if (!selectedTableName.value || !excelFile.value) return
  previewingExcel.value = true
  pageError.value = ''
  try {
    const preview = await previewExcel(selectedTableName.value, excelFile.value)
    excelPreview.value = preview
    importMapping.value = { ...preview.suggested_mapping }
  } catch (error: any) {
    pageError.value = errorMessage(error, t('admin.storage.failed_preview'))
  } finally {
    previewingExcel.value = false
  }
}

function resetImportState() {
  excelFile.value = null
  excelPreview.value = null
  importMapping.value = {}
  previewingExcel.value = false
}

function closeImportModal() {
  showImportModal.value = false
  resetImportState()
}

function sampleForHeader(header: string) {
  if (!excelPreview.value) return ''
  const index = excelPreview.value.headers.indexOf(header)
  if (index < 0) return ''
  const sample = excelPreview.value.sample_rows
    .map((row) => row[index])
    .find((value) => value !== null && value !== undefined && value !== '')
  return sample === undefined ? '' : String(sample)
}

function formatDate(value: string | null) {
  if (!value) return ''
  return new Date(value).toLocaleString()
}

type ColumnKind = 'text' | 'longtext' | 'json' | 'boolean' | 'datetime' | 'date' | 'time' | 'number'

function columnKind(column: StorageColumnInfo): ColumnKind {
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

function displayValue(value: any, column: StorageColumnInfo) {
  if (value === null || value === undefined || value === '') return '-'
  if (columnKind(column) === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function toFormValue(value: any, column: StorageColumnInfo): any {
  if (columnKind(column) === 'json' && value !== null && typeof value === 'object') {
    return JSON.stringify(value, null, 2)
  }
  return value ?? ''
}

function fromFormValue(value: any, column: StorageColumnInfo): any {
  if (columnKind(column) === 'json' && typeof value === 'string' && value.trim() !== '') {
    try {
      return JSON.parse(value)
    } catch {
      return value
    }
  }
  return value
}

let rowSearchTimer: ReturnType<typeof window.setTimeout> | null = null
watch(rowSearch, () => {
  if (rowSearchTimer) window.clearTimeout(rowSearchTimer)
  rowSearchTimer = window.setTimeout(() => {
    if (selectedTableName.value) {
      rowPage.value = 1
      loadRows()
    }
  }, 250)
})

onMounted(loadAllTables)
</script>

<template>
  <div class="storage-page">
    <div v-if="notice" class="storage-toast">{{ notice }}</div>
    <div v-if="pageError" class="storage-alert">{{ pageError }}</div>

    <div class="storage-layout" :class="{ 'storage-layout-wide': selectedTableName }">
      <section class="storage-panel" :class="{ 'mobile-pane-hidden': mobilePane === 'data' }">
        <header class="storage-panel-header">
          <div class="storage-title-row">
            <h2>{{ t('admin.storage.tables') }}</h2>
            <span class="storage-count">{{ filteredTables.length }}</span>
            <button class="storage-small-btn" @click="openCreateTable">{{ t('admin.storage.add') }}</button>
          </div>
          <input v-model="tableSearch" class="storage-search" type="search" :placeholder="t('admin.storage.search_tables')" />
        </header>
        <div class="storage-list">
          <div v-if="loadingTables" class="storage-empty">{{ t('admin.storage.loading_tables') }}</div>
          <div v-else-if="filteredTables.length === 0" class="storage-empty">{{ t('admin.storage.no_tables') }}</div>
          <div
            v-for="table in filteredTables"
            :key="table.name"
            class="storage-table-item"
            :class="{ selected: selectedTableName === table.name }"
            @click="selectTable(table.name)"
          >
            <div class="storage-item-content">
              <span class="storage-item-name">{{ table.name }}</span>
              <span v-if="table.description" class="storage-item-desc storage-item-about">{{ table.description }}</span>
              <span class="storage-item-desc">{{ table.columns?.length || 0 }} {{ t('admin.storage.columns').toLowerCase() }} &middot; {{ table.row_count }}</span>
              <div v-if="table.projects && table.projects.length" class="storage-project-badges">
                <span v-for="project in table.projects" :key="project.id" class="storage-project-badge">
                  {{ project.name }}
                </span>
              </div>
              <span v-if="table.is_system" class="storage-system-badge">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                {{ t('admin.storage.system_table') }}
              </span>
            </div>
            <div v-if="!table.is_system" class="storage-actions">
              <button class="storage-icon-btn" :title="t('admin.common.edit')" :aria-label="t('admin.common.edit')" @click.stop="openEditTable(table)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="storage-icon-btn danger" :title="t('admin.common.delete')" :aria-label="t('admin.common.delete')" @click.stop="removeTable(table)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="3 6 5 6 21 6"/>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
                  <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </section>

      <section v-if="selectedTableName" class="storage-panel storage-data-panel" :class="{ 'mobile-pane-hidden': mobilePane === 'tables' }">
        <header class="storage-panel-header">
          <button type="button" class="storage-mobile-back" @click="mobilePane = 'tables'">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" style="width:0.85rem;height:0.85rem"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" /></svg>
            <span>{{ t('admin.storage.tables') }}</span>
          </button>
          <div class="storage-title-row">
            <h2>{{ selectedTable?.name }} {{ t('admin.storage.data') }}</h2>
            <div class="storage-toolbar">
              <button class="storage-small-btn" @click="handleExport">{{ t('admin.storage.export') }}</button>
              <button class="storage-small-btn" @click="showImportModal = true">{{ t('admin.storage.import') }}</button>
              <button v-if="selectedRowIds.length > 0" class="storage-small-btn danger" @click="bulkDeleteRows">{{ t('admin.storage.delete_selected') }} ({{ selectedRowIds.length }})</button>
              <button class="storage-small-btn primary" :disabled="schemaColumns.length === 0" @click="openCreateRow">{{ t('admin.storage.add_row') }}</button>
            </div>
          </div>
          <input v-model="rowSearch" class="storage-search" type="search" :placeholder="t('admin.storage.search_rows')" />
        </header>

        <div class="storage-grid-wrap">
          <div v-if="loadingRows" class="storage-empty">{{ t('admin.storage.loading_rows') }}</div>
          <div v-else-if="schemaColumns.length === 0" class="storage-empty">{{ t('admin.storage.define_columns') }}</div>
          <template v-else>
          <table class="storage-grid">
            <thead>
              <tr>
                <th class="storage-grid-check">
                  <input type="checkbox" :checked="allRowsSelected" @change="toggleAllRows()" />
                </th>
                <th class="sortable" :class="{ 'sorted': sortBy === 'id' }" @click="toggleSort('id')">
                  id
                  <span v-if="sortBy === 'id'" class="sort-arrow">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path :d="sortArrowPath()" /></svg>
                  </span>
                </th>
                <th v-for="column in schemaColumns" :key="column.name" class="sortable" :class="{ 'sorted': sortBy === column.name }" :title="column.description || column.data_type" @click="toggleSort(column.name)">
                  <span class="column-title">{{ column.name }}</span>
                  <span class="column-description">{{ column.description || column.data_type }}</span>
                  <span v-if="sortBy === column.name" class="sort-arrow">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path :d="sortArrowPath()" /></svg>
                  </span>
                </th>
                <th class="sortable" :class="{ 'sorted': sortBy === 'created_at' }" @click="toggleSort('created_at')">
                  {{ t('admin.storage.created') }}
                  <span v-if="sortBy === 'created_at'" class="sort-arrow">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path :d="sortArrowPath()" /></svg>
                  </span>
                </th>
                <th class="sortable" :class="{ 'sorted': sortBy === 'updated_at' }" @click="toggleSort('updated_at')">
                  {{ t('admin.storage.updated') }}
                  <span v-if="sortBy === 'updated_at'" class="sort-arrow">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path :d="sortArrowPath()" /></svg>
                  </span>
                </th>
                <th class="grid-actions">{{ t('admin.common.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.id">
                <td class="storage-grid-check">
                  <input type="checkbox" :checked="selectedRowIds.includes(row.id)" @change="toggleRow(row.id)" />
                </td>
                <td class="row-id">{{ row.id }}</td>
                <td v-for="column in schemaColumns" :key="column.name" :title="displayValue(row.data[column.name], column)">
                  {{ displayValue(row.data[column.name], column) }}
                </td>
                <td>{{ formatDate(row.created_at) }}</td>
                <td>{{ formatDate(row.updated_at) }}</td>
                <td class="grid-actions">
                  <button class="storage-icon-btn" :title="t('admin.common.edit')" :aria-label="t('admin.common.edit')" @click="openEditRow(row)">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                      <path d="M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                  </button>
                  <button class="storage-icon-btn danger" :title="t('admin.common.delete')" :aria-label="t('admin.common.delete')" @click="removeRow(row)">
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
          <div v-if="rows.length === 0" class="storage-empty storage-empty-fill">{{ t('admin.storage.no_rows') }}</div>
          </template>
        </div>

        <div v-if="rowTotal > 0" class="storage-pagination">
          <span class="storage-page-total">{{ t('admin.storage.total_rows', { total: rowTotal }) }}</span>
          <label class="storage-page-size">
            <span>{{ t('admin.storage.per_page') }}</span>
            <select v-model="rowPerPage" class="storage-page-size-select" @change="onRowPerPageChange">
              <option :value="10">10</option>
              <option :value="25">25</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
              <option value="all">{{ t('admin.storage.all') }}</option>
            </select>
          </label>
          <template v-if="rowPages > 1">
            <button class="storage-small-btn" :disabled="rowPage <= 1" @click="prevPage">{{ t('admin.storage.prev_page') }}</button>
            <span class="storage-page-info">{{ t('admin.storage.page_x_of_y', { page: rowPage, pages: rowPages }) }}</span>
            <button class="storage-small-btn" :disabled="rowPage >= rowPages" @click="nextPage">{{ t('admin.storage.next_page') }}</button>
          </template>
        </div>
      </section>
    </div>

    <Teleport to="body">
      <div v-if="showTableModal" class="storage-overlay" @click.self="showTableModal = false">
        <div class="storage-modal storage-modal-lg">
          <header class="storage-modal-header">
            <h3>{{ editingTableName ? t('admin.storage.edit_table') : t('admin.storage.create_table') }}</h3>
            <button @click="showTableModal = false">{{ t('admin.common.close') }}</button>
          </header>
          <div class="storage-modal-body">
            <div v-if="tableError" class="storage-alert">{{ tableError }}</div>
            <label class="storage-field">
              <span>{{ t('admin.common.name') }}</span>
              <input v-model="tableName" class="storage-input" type="text" placeholder="my_custom_data" />
            </label>
            <label class="storage-field">
              <span>{{ t('admin.common.description') }}</span>
              <input v-model="tableDescription" class="storage-input" type="text" :placeholder="t('admin.storage.optional_description')" />
            </label>

            <div class="storage-column-header">
              <strong>{{ t('admin.storage.columns') }}</strong>
              <button class="storage-small-btn" @click="addColumn">{{ t('admin.storage.add_column') }}</button>
            </div>

            <div v-if="modalColumns.length === 0" class="storage-empty compact">{{ t('admin.storage.no_columns') }}</div>
            <div v-for="(column, index) in modalColumns" :key="index" class="storage-column-row">
              <input v-model="column.name" class="storage-input" type="text" placeholder="column_name" />
              <input v-model="column.description" class="storage-input description-input" type="text" :placeholder="t('admin.common.description')" />
              <select v-model="column.data_type" class="storage-input type-select">
                <option v-for="type in dataTypes" :key="type" :value="type">{{ type }}</option>
              </select>
              <input v-if="column.data_type === 'string'" v-model.number="column.length" class="storage-input length-input" type="number" min="1" :placeholder="t('admin.storage.length')" />
              <label class="nullable-check">
                <input v-model="column.nullable" type="checkbox" />
                {{ t('admin.storage.nullable') }}
              </label>
              <input v-model="column.default_value" class="storage-input default-input" type="text" :placeholder="t('admin.storage.default')" />
              <button class="storage-small-btn danger" @click="removeColumn(index)">{{ t('admin.storage.remove') }}</button>
            </div>
          </div>
          <footer class="storage-modal-footer">
            <button class="storage-small-btn" @click="showTableModal = false">{{ t('admin.common.cancel') }}</button>
            <button class="storage-small-btn primary" :disabled="tableSaving" @click="saveTable">
              {{ tableSaving ? t('admin.common.saving') : t('admin.storage.save_table') }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showRowModal" class="storage-overlay" @click.self="showRowModal = false">
        <div class="storage-modal">
          <header class="storage-modal-header">
            <h3>{{ editingRowId ? t('admin.storage.edit_row') : t('admin.storage.create_row') }}</h3>
            <button @click="showRowModal = false">{{ t('admin.common.close') }}</button>
          </header>
          <div class="storage-modal-body">
            <div v-if="rowError" class="storage-alert">{{ rowError }}</div>
            <label v-for="column in schemaColumns" :key="column.name" class="storage-field">
              <span>{{ column.name }} <small>{{ column.data_type }}</small></span>
              <textarea
                v-if="['longtext', 'json'].includes(columnKind(column))"
                v-model="rowData[column.name]"
                class="storage-input textarea"
              />
              <select v-else-if="columnKind(column) === 'boolean'" v-model="rowData[column.name]" class="storage-input">
                <option value="">-</option>
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
              <input
                v-else-if="columnKind(column) === 'datetime'"
                v-model="rowData[column.name]"
                class="storage-input"
                type="datetime-local"
              />
              <input v-else-if="columnKind(column) === 'date'" v-model="rowData[column.name]" class="storage-input" type="date" />
              <input v-else-if="columnKind(column) === 'time'" v-model="rowData[column.name]" class="storage-input" type="time" />
              <input
                v-else-if="columnKind(column) === 'number'"
                v-model="rowData[column.name]"
                class="storage-input"
                type="number"
                step="any"
              />
              <input v-else v-model="rowData[column.name]" class="storage-input" type="text" />
            </label>
          </div>
          <footer class="storage-modal-footer">
            <button class="storage-small-btn" @click="showRowModal = false">{{ t('admin.common.cancel') }}</button>
            <button class="storage-small-btn primary" :disabled="rowSaving" @click="saveRow">
              {{ rowSaving ? t('admin.common.saving') : t('admin.storage.save_row') }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showImportModal" class="storage-overlay" @click.self="closeImportModal">
        <div class="storage-modal storage-modal-lg">
          <header class="storage-modal-header">
            <h3>{{ t('admin.storage.import_excel') }}</h3>
            <button @click="closeImportModal">{{ t('admin.common.close') }}</button>
          </header>
          <div class="storage-modal-body">
            <p class="storage-help">{{ t('admin.storage.upload_help') }}</p>
            <input class="storage-input" type="file" accept=".xlsx" @change="onExcelFileChange" />
            <p v-if="excelFile" class="storage-file-name">{{ excelFile.name }}</p>

            <div v-if="previewingExcel" class="storage-empty compact">{{ t('admin.storage.reading_workbook') }}</div>
            <div v-else-if="excelPreview" class="mapping-panel">
              <div class="mapping-header">
                <span>{{ t('admin.storage.database_column') }}</span>
                <span>{{ t('admin.storage.excel_column') }}</span>
              </div>
              <div v-for="column in schemaColumns" :key="column.name" class="mapping-row">
                <div class="mapping-db-col">
                  <strong>{{ column.name }}</strong>
                  <span>{{ column.data_type }}</span>
                </div>
                <div class="mapping-select-wrap">
                  <select v-model="importMapping[column.name]" class="storage-input">
                    <option value="">{{ t('admin.storage.do_not_import') }}</option>
                    <option v-for="header in excelPreview.headers" :key="header" :value="header">
                      {{ header }}
                    </option>
                  </select>
                  <span v-if="importMapping[column.name]" class="mapping-sample">
                    {{ t('admin.storage.sample', { value: sampleForHeader(importMapping[column.name]) || '-' }) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <footer class="storage-modal-footer">
            <button class="storage-small-btn" @click="closeImportModal">{{ t('admin.common.cancel') }}</button>
            <button class="storage-small-btn primary" :disabled="importing || !excelFile || !excelPreview" @click="handleImport">
              {{ importing ? t('admin.storage.importing') : t('admin.storage.import') }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.storage-page {
  padding: 1rem;
  height: var(--shell-content-height);
  overflow: auto;
}
.storage-layout {
  display: grid;
  grid-template-columns: 20rem 1fr;
  gap: 1rem;
  min-width: 860px;
  height: 100%;
}
.storage-layout-wide {
  grid-template-columns: 20rem minmax(0, 1fr);
}
.storage-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}
.storage-data-panel {
  min-width: 30rem;
}
.storage-panel-header {
  flex-shrink: 0;
  padding: 0.75rem;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}
.storage-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.storage-title-row h2 {
  margin: 0;
  font-size: 0.9rem;
  color: #334155;
}
.storage-count,
.storage-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: #475569;
  background: #f1f5f9;
  border-radius: 999px;
  padding: 0.15rem 0.45rem;
  align-self: flex-start;
}
.storage-context,
.storage-item-desc {
  font-size: 0.75rem;
  color: #64748b;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.storage-item-about {
  color: #94a3b8;
}
.storage-search,
.storage-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  color: #0f172a;
  font-size: 0.82rem;
  padding: 0.45rem 0.6rem;
  outline: none;
}
.storage-search:focus,
.storage-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
}
.storage-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.storage-item,
.storage-table-item {
  width: 100%;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: inherit;
  text-align: left;
  padding: 0.55rem 0.65rem;
  cursor: pointer;
  display: flex;
  gap: 0.5rem;
}
.storage-item {
  flex-direction: column;
}
.storage-table-item {
  align-items: flex-start;
}
.storage-item:hover,
.storage-table-item:hover {
  background: #f8fafc;
}
.storage-item.selected,
.storage-table-item.selected {
  background: #eef2ff;
  border-color: #a5b4fc;
}
.storage-item-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.storage-item-name {
  font-size: 0.83rem;
  font-weight: 600;
  color: #0f172a;
  overflow-wrap: anywhere;
}
.storage-actions,
.grid-actions,
.storage-toolbar {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}
.storage-actions {
  flex-direction: row;
  flex-shrink: 0;
}
.storage-icon-btn {
  width: 1.5rem;
  height: 1.5rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  border-radius: 4px;
  padding: 0;
  flex-shrink: 0;
}
.storage-icon-btn:hover {
  color: #4f46e5;
  background: #eef2ff;
}
.storage-icon-btn.danger:hover {
  color: #dc2626;
  background: #fef2f2;
}
.storage-small-btn {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #334155;
  border-radius: 6px;
  padding: 0.36rem 0.62rem;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.storage-small-btn:hover {
  background: #f8fafc;
}
.storage-small-btn.primary {
  background: #6366f1;
  border-color: #6366f1;
  color: #fff;
}
.storage-small-btn.primary:hover {
  background: #4f46e5;
}
.storage-small-btn.danger {
  color: #dc2626;
  border-color: #fecaca;
}
.storage-small-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.storage-pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 0.75rem;
}
.storage-page-info {
  font-size: 0.82rem;
  color: #64748b;
  white-space: nowrap;
}
.storage-page-total {
  font-size: 0.78rem;
  color: #94a3b8;
  margin-right: auto;
  white-space: nowrap;
}
.storage-page-size {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.78rem;
  color: #64748b;
  white-space: nowrap;
}
.storage-page-size-select {
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  color: #0f172a;
  font-size: 0.8rem;
  padding: 0.28rem 0.5rem;
  outline: none;
  cursor: pointer;
}
.storage-grid-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}
.storage-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}
.storage-grid th,
.storage-grid td {
  border-bottom: 1px solid #e2e8f0;
  padding: 0.55rem 0.7rem;
  text-align: left;
  max-width: 16rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.storage-grid th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f8fafc;
  color: #475569;
  font-weight: 700;
}
.storage-grid th.grid-actions,
.storage-grid td.grid-actions {
  display: table-cell;
  width: 6.5rem;
  max-width: 6.5rem;
  vertical-align: middle;
}
.storage-grid td.grid-actions button {
  line-height: 1;
  vertical-align: middle;
}
.column-title,
.column-description {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
}
.column-description {
  margin-top: 0.12rem;
  color: #94a3b8;
  font-size: 0.68rem;
  font-weight: 500;
  max-width: 14rem;
}
.storage-grid-check {
  width: 2.25rem;
  text-align: center;
}
.storage-grid-check input[type="checkbox"] {
  width: 0.95rem;
  height: 0.95rem;
  accent-color: #6366f1;
  cursor: pointer;
  vertical-align: middle;
}
.row-id {
  color: #94a3b8;
  font-weight: 700;
}
.storage-grid th.sortable {
  cursor: pointer;
  user-select: none;
}
.storage-grid th.sortable:hover {
  color: #1e40af;
}
.storage-grid th.sortable.sorted {
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
.storage-empty,
.storage-empty-cell {
  color: #94a3b8;
  font-size: 0.85rem;
  text-align: center;
  padding: 2rem 1rem;
}
.storage-grid-wrap > .storage-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
}
.storage-empty.compact {
  padding: 0.8rem;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
}
.storage-alert {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  border-radius: 8px;
  padding: 0.6rem 0.75rem;
  font-size: 0.82rem;
  margin-bottom: 0.75rem;
}
.storage-toast {
  position: fixed;
  right: 1rem;
  top: 4.5rem;
  z-index: 1200;
  background: #0f172a;
  color: #fff;
  border-radius: 8px;
  padding: 0.65rem 0.9rem;
  font-size: 0.82rem;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.2);
}
.storage-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: rgba(15, 23, 42, 0.52);
}
.storage-modal {
  width: min(92vw, 36rem);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.25);
}
.storage-modal-lg {
  width: min(94vw, 58rem);
}
.storage-modal-header,
.storage-modal-footer {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.9rem 1rem;
  border-bottom: 1px solid #e2e8f0;
}
.storage-modal-footer {
  justify-content: flex-end;
  border-top: 1px solid #e2e8f0;
  border-bottom: none;
}
.storage-modal-header h3 {
  margin: 0;
  color: #0f172a;
  font-size: 1rem;
}
.storage-modal-header button {
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-weight: 600;
}
.storage-modal-body {
  overflow-y: auto;
  padding: 1rem;
}
.storage-field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-bottom: 0.85rem;
}
.storage-field span {
  font-size: 0.8rem;
  font-weight: 700;
  color: #334155;
}
.storage-field small {
  color: #94a3b8;
  font-weight: 500;
}
.textarea {
  min-height: 5rem;
  resize: vertical;
}
.storage-help {
  margin: 0 0 0.75rem;
  color: #64748b;
  font-size: 0.84rem;
}
.storage-file-name {
  margin: 0.65rem 0 0;
  color: #334155;
  font-size: 0.82rem;
  font-weight: 600;
}
.mapping-panel {
  margin-top: 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}
.mapping-header,
.mapping-row {
  display: grid;
  grid-template-columns: minmax(12rem, 0.9fr) minmax(14rem, 1.1fr);
  gap: 0.75rem;
  align-items: center;
}
.mapping-header {
  background: #f8fafc;
  color: #475569;
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.55rem 0.75rem;
  border-bottom: 1px solid #e2e8f0;
}
.mapping-row {
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid #f1f5f9;
}
.mapping-row:last-child {
  border-bottom: none;
}
.mapping-db-col,
.mapping-select-wrap {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.18rem;
}
.mapping-db-col strong {
  color: #0f172a;
  font-size: 0.82rem;
}
.mapping-db-col span,
.mapping-sample {
  color: #64748b;
  font-size: 0.72rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.storage-column-header,
.storage-column-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.storage-column-header {
  justify-content: space-between;
  margin: 1rem 0 0.6rem;
}
.storage-column-row {
  padding: 0.45rem 0;
  border-bottom: 1px solid #f1f5f9;
}
.storage-reorder {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.storage-reorder button {
  border: none;
  background: #f1f5f9;
  border-radius: 4px;
  color: #64748b;
  font-size: 0.62rem;
  cursor: pointer;
}
.type-select {
  max-width: 8rem;
}
.description-input {
  min-width: 11rem;
}
.length-input {
  max-width: 5rem;
}
.default-input {
  max-width: 7rem;
}
.nullable-check {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  color: #475569;
  font-size: 0.76rem;
  white-space: nowrap;
}
@media (max-width: 900px) {
  .storage-page {
    height: auto;
  }
  .storage-layout,
  .storage-layout-wide {
    grid-template-columns: 1fr;
    min-width: 0;
  }
  .storage-data-panel {
    min-width: 0;
    min-height: 28rem;
  }
  .storage-column-row {
    align-items: stretch;
    flex-direction: column;
  }
  .type-select,
  .length-input,
  .default-input {
    max-width: none;
  }
}

.storage-project-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-top: 0.35rem;
}
/*
 * The chip names the project a table is shared with, so it has to be legible at
 * 0.7rem. --accent is the near-white lavender meant for backgrounds, and using
 * it as the text colour left these almost invisible; the readable pairing is
 * --accent-foreground on --accent.
 */
.storage-project-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--accent-foreground, hsl(266 50% 38%));
  background: var(--accent, hsl(266 50% 95%));
  border: 1px solid color-mix(in srgb, var(--accent-foreground, hsl(266 50% 38%)) 35%, transparent);
  border-radius: 999px;
  padding: 0.1rem 0.5rem;
}
.storage-system-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  margin-top: 0.35rem;
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #92400e;
  background: #fef3c7;
  border: 1px solid #f59e0b;
  border-radius: 999px;
  padding: 0.12rem 0.6rem;
  box-shadow: 0 1px 2px rgba(146, 64, 14, 0.18);
}
.storage-project-badge.muted {
  color: #94a3b8;
  background: #f1f5f9;
  border-color: #e2e8f0;
}
.storage-project-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem;
  padding: 0.4rem 0;
  border-bottom: 1px solid var(--border, #e2e8f0);
  margin-bottom: 0.5rem;
}
.storage-project-bar-label {
  font-size: 0.75rem;
  color: #64748b;
  font-weight: 600;
}
.storage-project-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.75rem;
  color: #0f172a;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  padding: 0.15rem 0.5rem;
}
.storage-project-tag.muted {
  color: #94a3b8;
  background: transparent;
}
.storage-project-tag-remove {
  border: none;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  font-size: 0.9rem;
  line-height: 1;
  padding: 0;
}
.storage-project-tag-remove:hover {
  color: #dc2626;
}
.storage-project-add {
  max-width: 12rem;
  padding: 0.2rem 0.4rem;
  font-size: 0.75rem;
}
.storage-project-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  max-height: 8rem;
  overflow-y: auto;
  padding: 0.25rem 0;
}
.storage-project-check {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.8rem;
  color: #334155;
  cursor: pointer;
}

/* The step back only exists where the panes are shown one at a time. */
.storage-mobile-back { display: none; }

/* Phones show the list and the rows one at a time. Stacked, the rows sat
   thousands of pixels below the list, so tapping a table looked like it did
   nothing; the data header now carries the way back. */
@media (max-width: 767px) {
  .mobile-pane-hidden { display: none !important; }

  .storage-mobile-back {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    align-self: flex-start;
    padding: 0.3rem 0.6rem;
    font-size: 0.78rem;
    font-weight: 600;
    color: #4338ca;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 0.6rem;
    cursor: pointer;
  }
  .storage-mobile-back:hover { background: #f9fafb; }
}
</style>
