import api from './client'
import type { StorageRow, StorageTableCreate, StorageTableInfo, StorageTableUpdate } from '../types'

export interface ExcelPreview {
  headers: string[]
  sample_rows: any[][]
  database_columns: Array<{
    name: string
    description: string | null
    data_type: string
    nullable: boolean
  }>
  suggested_mapping: Record<string, string>
}

export interface StorageRowPage {
  items: StorageRow[]
  total: number
  page: number
  per_page: number
  pages: number
}

const storageBase = '/admin/storage'

export async function fetchAllTables(): Promise<StorageTableInfo[]> {
  const res = await api.get(`${storageBase}/tables`)
  return res.data
}

export async function createTable(payload: StorageTableCreate): Promise<StorageTableInfo> {
  const res = await api.post(`${storageBase}/tables`, payload)
  return res.data
}

export async function updateTable(tableName: string, payload: StorageTableUpdate): Promise<StorageTableInfo> {
  const res = await api.put(`${storageBase}/tables/${encodeURIComponent(tableName)}`, payload)
  return res.data
}

export async function deleteTable(tableName: string): Promise<void> {
  await api.delete(`${storageBase}/tables/${encodeURIComponent(tableName)}`)
}

export async function fetchRows(
  tableName: string,
  search = '',
  page = 1,
  perPage: number | 'all' = 50,
  sortBy = 'id',
  sortDir: 'asc' | 'desc' = 'asc',
): Promise<StorageRowPage> {
  const res = await api.get(`${storageBase}/tables/${encodeURIComponent(tableName)}/rows`, {
    params: { search, page, per_page: perPage, sort_by: sortBy, sort_dir: sortDir },
  })
  return res.data
}

export async function createRow(tableName: string, data: Record<string, any>): Promise<StorageRow> {
  const res = await api.post(`${storageBase}/tables/${encodeURIComponent(tableName)}/rows`, { data })
  return res.data
}

export async function updateRow(tableName: string, rowId: number, data: Record<string, any>): Promise<StorageRow> {
  const res = await api.put(`${storageBase}/tables/${encodeURIComponent(tableName)}/rows/${rowId}`, { data })
  return res.data
}

export async function deleteRow(tableName: string, rowId: number): Promise<void> {
  await api.delete(`${storageBase}/tables/${encodeURIComponent(tableName)}/rows/${rowId}`)
}

export async function previewExcel(tableName: string, file: File): Promise<ExcelPreview> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post(`${storageBase}/tables/${encodeURIComponent(tableName)}/preview-excel`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function importExcel(
  tableName: string,
  file: File,
  mapping: Record<string, string>,
): Promise<{ imported: number }> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('mapping', JSON.stringify(mapping))
  const res = await api.post(`${storageBase}/tables/${encodeURIComponent(tableName)}/import-excel`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function exportExcel(tableName: string): Promise<Blob> {
  const res = await api.get(`${storageBase}/tables/${encodeURIComponent(tableName)}/export-excel`, {
    responseType: 'blob',
  })
  return res.data
}
