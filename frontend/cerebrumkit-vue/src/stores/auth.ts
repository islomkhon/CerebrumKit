import { defineStore } from 'pinia'
import { ref } from 'vue'
import { login, register } from '../api/auth'
import type { User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref<User | null>(parseUserFromStorage())
  const isAuthenticated = ref(!!token.value)

  function parseUserFromStorage(): User | null {
    try {
      const raw = localStorage.getItem('user')
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  }

  async function signIn(email: string, password: string) {
    const res = await login(email, password)
    token.value = res.access_token
    user.value = res.user
    localStorage.setItem('token', res.access_token)
    localStorage.setItem('user', JSON.stringify(res.user))
    isAuthenticated.value = true
  }

  async function signUp(data: Partial<User> & { password: string }) {
    await register(data)
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    isAuthenticated.value = false
  }

  return { token, user, isAuthenticated, signIn, signUp, logout }
})
