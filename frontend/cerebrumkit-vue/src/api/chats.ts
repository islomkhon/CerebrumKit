import api from './client'
import type { Chat, Message, Project } from '../types'

// Chat history is paged. A reader opens on the newest messages and older pages
// arrive as they scroll up, so every history call returns one page plus the
// flag that says whether an older page exists.
// `beforeId` is the id of the oldest row already held; rows are paged by id
// because `created_at` is not unique.
export interface MessagePageParams {
  limit?: number
  beforeId?: number
  includeDebug?: boolean
}

export interface MessagePage {
  messages: Message[]
  has_more: boolean
}

function messagePageQuery(params?: MessagePageParams) {
  const query: Record<string, number | boolean> = {}
  if (params?.limit != null) query.limit = params.limit
  if (params?.beforeId != null) query.before_id = params.beforeId
  if (params?.includeDebug != null) query.include_debug = params.includeDebug
  return query
}

export async function fetchAdminUserChats(projectId: number, userId: number): Promise<Chat[]> {
  const res = await api.get(`/admin/projects/${projectId}/users/${userId}/chats`)
  return res.data
}

export async function createAdminChat(projectId: number, userId: number, description: string): Promise<Chat> {
  const res = await api.post(`/admin/projects/${projectId}/users/${userId}/chats`, { description })
  return res.data
}

export async function fetchAdminChatMessages(
  projectId: number,
  userId: number,
  chatId: number,
  params?: MessagePageParams,
): Promise<MessagePage> {
  const res = await api.get(`/admin/projects/${projectId}/users/${userId}/chats/${chatId}/messages`, {
    params: messagePageQuery(params),
  })
  return res.data
}

export async function createChat(data: Partial<Chat>): Promise<Chat> {
  const res = await api.post('/chats', data)
  return res.data
}

export async function fetchMessages(chatId: number, params?: MessagePageParams): Promise<MessagePage> {
  const res = await api.get(`/chats/${chatId}/messages`, { params: messagePageQuery(params) })
  return res.data
}
// Keep old fetch functions for non-admin usage
export async function sendMessage(chatId: number, data: Partial<Message>): Promise<Message> {
  const res = await api.post(`/chats/${chatId}/messages`, data)
  return res.data
}

export async function sendAdminChatMessage(projectId: number, userId: number, chatId: number, data: Partial<Message>): Promise<Message> {
  const res = await api.post(`/admin/projects/${projectId}/users/${userId}/chats/${chatId}/messages`, data)
  return res.data
}

// ── Client chat API ────────────────────────────────────────────

export async function fetchClientProjects(search?: string): Promise<Project[]> {
  const params: Record<string, string> = {}
  if (search) params.search = search
  const res = await api.get('/client/projects', { params })
  return res.data
}

export async function fetchClientChats(projectId: number): Promise<Chat[]> {
  const res = await api.get(`/client/projects/${projectId}/chats`)
  return res.data
}

export async function createClientChat(projectId: number, description: string): Promise<Chat> {
  const res = await api.post(`/client/projects/${projectId}/chats`, { description })
  return res.data
}

export async function updateClientChat(projectId: number, chatId: number, data: Partial<Chat>): Promise<Chat> {
  const res = await api.put(`/client/projects/${projectId}/chats/${chatId}`, data)
  return res.data
}

export async function deleteClientChat(projectId: number, chatId: number): Promise<void> {
  await api.delete(`/client/projects/${projectId}/chats/${chatId}`)
}

export async function fetchClientChatMessages(
  projectId: number,
  chatId: number,
  params?: MessagePageParams,
): Promise<MessagePage> {
  const res = await api.get(`/client/projects/${projectId}/chats/${chatId}/messages`, {
    params: messagePageQuery(params),
  })
  return res.data
}

export async function sendClientChatMessage(projectId: number, chatId: number, data: Partial<Message>): Promise<Message> {
  const res = await api.post(`/client/projects/${projectId}/chats/${chatId}/messages`, data)
  return res.data
}
