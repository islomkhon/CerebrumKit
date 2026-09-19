<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import AppIcon from '../components/AppIcon.vue'

const auth = useAuthStore()
const router = useRouter()
const { t } = useI18n()

const email = ref('')
const password = ref('')
const error = ref('')
const route = useRoute()

async function handleLogin() {
  try {
    error.value = ''
    await auth.signIn(email.value, password.value)
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
      ? route.query.redirect
      : ''
    router.push(redirect || (auth.user?.role === 'admin' ? '/admin/projects' : '/client/projects'))
  } catch (e: any) {
    error.value = e.response?.data?.detail || 'Login failed'
  }
}
</script>

<template>
  <div class="login">
    <form @submit.prevent="handleLogin" class="login-card">
      <h1 class="login-brand">
        <AppIcon name="brand" class="login-mark" />
        <span>{{ t('nav.brand') }}</span>
      </h1>
      <p class="subtitle">{{ t('auth.login_title') }}</p>

      <div v-if="error" class="error">{{ error }}</div>

      <label>{{ t('auth.email') }}</label>
      <input v-model="email" type="email" placeholder="you@example.com" required />

      <label>{{ t('auth.password') }}</label>
      <input v-model="password" type="password" placeholder="••••••••" required />

      <button type="submit" class="btn-signin">{{ t('auth.sign_in') }}</button>
    </form>
  </div>
</template>

<style scoped>
.login {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: #f1f5f9;
}
.login-card {
  background: white;
  padding: 2.5rem;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
  width: 380px;
}
h1 {
  margin: 0 0 0.25rem;
  font-size: 1.6rem;
}
.login-brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #312e81;
  letter-spacing: -0.01em;
}
.login-brand .login-mark {
  width: 1.8rem;
  height: 1.8rem;
  color: #6366f1;
}
.subtitle {
  color: #64748b;
  margin-top: 0;
  margin-bottom: 1.5rem;
}
label {
  display: block;
  font-size: 0.85rem;
  font-weight: 600;
  margin: 0.75rem 0 0.25rem;
  color: #334155;
}
input {
  width: 100%;
  padding: 0.6rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 0.95rem;
  box-sizing: border-box;
}
.btn-signin {
  width: 100%;
  margin-top: 1.25rem;
  padding: 0.7rem;
  background: #6366f1;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
}
.btn-signin:hover {
  background: #4f46e5;
}
.error {
  background: #fee2e2;
  color: #991b1b;
  padding: 0.5rem;
  border-radius: 6px;
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
}
</style>
