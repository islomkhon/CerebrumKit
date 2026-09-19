import api from './client'
import type { LoginResponse, User } from '../types'

export async function login(email: string, password: string): Promise<LoginResponse> {
  const res = await api.post('/auth/login', { email, password })
  return res.data
}

export async function register(data: Partial<User> & { password: string }): Promise<User> {
  const res = await api.post('/auth/register', data)
  return res.data
}
