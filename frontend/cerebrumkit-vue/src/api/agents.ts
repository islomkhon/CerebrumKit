import api from './client'
import type { Agent, Skill, Tool } from '../types'

const adminBase = '/admin'

export async function updateAgent(id: number, data: Partial<Agent>): Promise<Agent> {
  const res = await api.put(`${adminBase}/agents/${id}`, data)
  return res.data
}

export async function deleteAgent(id: number): Promise<void> {
  await api.delete(`${adminBase}/agents/${id}`)
}

export async function fetchSkills(): Promise<Skill[]> {
  const res = await api.get(`${adminBase}/skills`)
  return res.data
}

export async function createSkill(data: Partial<Skill>): Promise<Skill> {
  const res = await api.post(`${adminBase}/skills`, data)
  return res.data
}

export async function updateSkill(id: number, data: Partial<Skill>): Promise<Skill> {
  const res = await api.put(`${adminBase}/skills/${id}`, data)
  return res.data
}

export async function deleteSkill(id: number): Promise<void> {
  await api.delete(`${adminBase}/skills/${id}`)
}

export async function fetchTools(): Promise<Tool[]> {
  const res = await api.get(`${adminBase}/tools`)
  return res.data
}

export async function createTool(data: Partial<Tool>): Promise<Tool> {
  const res = await api.post(`${adminBase}/tools`, data)
  return res.data
}

export async function updateTool(id: number, data: Partial<Tool>): Promise<Tool> {
  const res = await api.put(`${adminBase}/tools/${id}`, data)
  return res.data
}

export async function deleteTool(id: number): Promise<void> {
  await api.delete(`${adminBase}/tools/${id}`)
}
