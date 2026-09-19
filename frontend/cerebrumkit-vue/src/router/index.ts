import { createRouter, createWebHistory } from 'vue-router'

// Views are lazy-loaded to avoid circular imports with the api layer
const LoginView = () => import('../views/LoginView.vue')
const AppLayout = () => import('../components/AppLayout.vue')

// Admin views
const AdminProjectsView = () => import('../views/admin/ProjectsView.vue')
const AdminStorageView = () => import('../views/admin/StorageView.vue')
const AdminUsersView = () => import('../views/admin/UsersView.vue')
const AdminSkillsView = () => import('../views/admin/SkillsView.vue')
const AdminToolsView = () => import('../views/admin/ToolsView.vue')
const AdminSettingsView = () => import('../views/admin/SettingsView.vue')
const AdminDocsView = () => import('../views/admin/DocsView.vue')

// Client views
const ClientProjectsView = () => import('../views/client/ProjectsView.vue')

import { useAuthStore } from '../stores/auth'

/**
 * Where a signed-in user belongs. Both the router guard and the catch-all route
 * send people here, so the two can never disagree about the default page.
 */
function homeFor(role: string | undefined): string | null {
  if (role === 'admin') return '/admin/projects'
  if (role === 'client') return '/client/projects'
  return null
}

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', name: 'Login', component: LoginView },

  // Admin routes
  {
    path: '/admin',
    component: AppLayout,
    meta: { requiresAuth: true, roles: ['admin'] },
    children: [
      { path: '', redirect: '/admin/projects' },
      { path: 'projects', name: 'AdminProjects', component: AdminProjectsView },
      { path: 'skills', name: 'AdminSkills', component: AdminSkillsView },
      { path: 'tools', name: 'AdminTools', component: AdminToolsView },
      { path: 'storage', name: 'AdminStorage', component: AdminStorageView },
      { path: 'users', name: 'AdminUsers', component: AdminUsersView },
      { path: 'settings', name: 'AdminSettings', component: AdminSettingsView },
      { path: 'docs', name: 'AdminDocs', component: AdminDocsView },
    ],
  },

  // Client routes
  {
    path: '/client',
    component: AppLayout,
    meta: { requiresAuth: true, roles: ['client'] },
    children: [
      { path: '', redirect: '/client/projects' },
      { path: 'projects', name: 'ClientProjects', component: ClientProjectsView },
    ],
  },

  // Catch-all -> send people to their own default page, or to the sign-in form.
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    redirect: () => homeFor(useAuthStore().user?.role) ?? '/login',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const auth = useAuthStore()
  // Token without user data is a stale/partial session - treat as logged out
  const hasSession = auth.isAuthenticated && !!auth.user
  const role = auth.user?.role

  // Public page -> a signed-in user goes straight to their own panel
  if (to.name === 'Login') {
    const home = homeFor(role)
    if (hasSession && home) return next(home)
    return next()
  }

  // Protected pages - require a valid session, otherwise go to login
  if (to.meta.requiresAuth) {
    if (!hasSession) {
      if (auth.isAuthenticated) auth.logout()
      return next({ path: '/login', query: { redirect: to.fullPath } })
    }

    const allowedRoles = to.meta.roles as string[] | undefined
    if (allowedRoles && role && !allowedRoles.includes(role)) {
      const home = homeFor(role)
      if (home) return next(home)
    }
  }

  next()
})

export default router
