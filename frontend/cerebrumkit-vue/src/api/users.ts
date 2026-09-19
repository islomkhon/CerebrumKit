import apiClient from './client'
import type { User } from '../types'

export function fetchUsers(): Promise<User[]> {
  return apiClient.get('/auth/users').then(r => r.data)
}

export function fetchAdminUsers(): Promise<User[]> {
  return apiClient.get('/admin/users').then(r => r.data)
}

export function createUser(data: Partial<User> & { password: string }): Promise<User> {
  return apiClient.post('/admin/users', data).then(r => r.data)
}

export function updateUser(id: number, data: Partial<User> & { password?: string }): Promise<User> {
  return apiClient.put(`/admin/users/${id}`, data).then(r => r.data)
}

export function deleteUser(id: number): Promise<void> {
  return apiClient.delete(`/admin/users/${id}`)
}
