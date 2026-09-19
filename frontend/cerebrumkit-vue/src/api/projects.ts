import api from './client'
import type { Project } from '../types'

export async function fetchProjects(): Promise<Project[]> {
  const res = await api.get('/admin/projects')
  return res.data
}

export async function createProject(data: Partial<Project>): Promise<Project> {
  const res = await api.post('/admin/projects', data)
  return res.data
}
