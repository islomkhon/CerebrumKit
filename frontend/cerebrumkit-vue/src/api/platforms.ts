import apiClient from './client'
import type { Platform, PlatformTestResult } from '../types'

export type PlatformInput = Omit<Platform, 'id' | 'effective'>

export function fetchPlatforms(): Promise<Platform[]> {
  return apiClient.get('/admin/platforms').then(r => r.data)
}

export function createPlatform(data: PlatformInput): Promise<Platform> {
  return apiClient.post('/admin/platforms', data).then(r => r.data)
}

export function updatePlatform(id: number, data: PlatformInput): Promise<Platform> {
  return apiClient.put(`/admin/platforms/${id}`, data).then(r => r.data)
}

export function deletePlatform(id: number): Promise<void> {
  return apiClient.delete(`/admin/platforms/${id}`)
}

export function activatePlatform(id: number): Promise<Platform> {
  return apiClient.post(`/admin/platforms/${id}/activate`).then(r => r.data)
}

export function testPlatform(id: number): Promise<PlatformTestResult> {
  return apiClient.post(`/admin/platforms/${id}/test`, null, { timeout: 60000 }).then(r => r.data)
}
