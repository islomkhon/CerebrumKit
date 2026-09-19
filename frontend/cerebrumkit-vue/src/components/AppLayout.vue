<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import AppIcon from './AppIcon.vue'

const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const auth = useAuthStore()

/** Locale code => native language name, matching the panel's switcher. */
const LOCALES: Record<string, string> = {
  en: 'English',
  ru: 'Русский',
  zh: '中文',
  es: 'Español',
  de: 'Deutsch',
  fr: 'Français',
}

const SIDEBAR_STATE_KEY = 'sidebar_state'

const isAdmin = computed(() => auth.user?.role === 'admin')

type NavItem = { routeName: string; labelKey: string; icon: string }

// Projects scope the work, skills and tools define what an agent can do, and
// storage holds the data those tools read and write.
const adminNav: NavItem[] = [
  { routeName: 'AdminProjects', labelKey: 'admin.sidebar.projects', icon: 'chat' },
  { routeName: 'AdminSkills', labelKey: 'admin.sidebar.skills', icon: 'sparkles' },
  { routeName: 'AdminTools', labelKey: 'admin.sidebar.tools', icon: 'wrench' },
  { routeName: 'AdminStorage', labelKey: 'admin.sidebar.storage', icon: 'database' },
  { routeName: 'AdminUsers', labelKey: 'admin.sidebar.users', icon: 'users' },
  { routeName: 'AdminSettings', labelKey: 'admin.sidebar.settings', icon: 'sliders-horizontal' },
  { routeName: 'AdminDocs', labelKey: 'admin.sidebar.docs', icon: 'book-open' },
]

// The client panel is where the people a project is built for work: they reach
// their own projects and talk to the agents in them, and nothing else.
const clientNav: NavItem[] = [
  { routeName: 'ClientProjects', labelKey: 'client.sidebar.projects', icon: 'chat' },
]

const navItems = computed(() => (isAdmin.value ? adminNav : clientNav))

/* ── Rail state ─────────────────────────────────────────────── */

const collapsed = ref(localStorage.getItem(SIDEBAR_STATE_KEY) === 'collapsed')
const mobileOpen = ref(false)
const langOpen = ref(false)

const narrowViewport = window.matchMedia('(max-width: 767px)')
const isMobile = ref(narrowViewport.matches)

/* ── Rail width ─────────────────────────────────────────────── */

/*
 * The rail hugs its content. A label is as long as its translation makes it, so
 * one fixed width either clips the text or leaves the rail half empty. The
 * width is measured from an off-screen copy of the same rows, with the same CSS.
 */
const RAIL_MIN_WIDTH = 160 // The 10rem the rail used to be pinned to.
const RAIL_MAX_WIDTH = 320 // Past this the rail stops earning its screen space.

const railRuler = ref<HTMLElement | null>(null)
const railWidth = ref(0)

const railRulerRows = computed(() => [
  ...navItems.value.map((item) => ({ key: item.routeName, icon: item.icon, label: t(item.labelKey) })),
  { key: 'language', icon: 'languages', label: LOCALES[locale.value] || 'English' },
  { key: 'sign-out', icon: 'log-out', label: t('auth.sign_out') },
])

const railStyle = computed(() =>
  railWidth.value ? { '--sidebar-width': `${railWidth.value}px` } : undefined,
)

// What the rail spends outside a row: its own padding plus the panel's. Read
// from the live elements because the phone drawer drops the outer gutter.
function railChrome() {
  const aside = document.querySelector('.sidebar')
  const content = document.querySelector('.sidebar-content')
  if (!aside || !content) return 0
  const padding = (el: Element) => {
    const style = getComputedStyle(el)
    return parseFloat(style.paddingLeft) + parseFloat(style.paddingRight)
  }
  return padding(aside) + padding(content)
}

function measureRail() {
  const rows = railRuler.value?.querySelectorAll<HTMLElement>('.nav-item')
  if (!rows || rows.length === 0) return
  let widest = 0
  rows.forEach((row) => {
    widest = Math.max(widest, row.getBoundingClientRect().width)
  })
  if (!widest) return
  const wanted = Math.ceil(widest + railChrome())
  railWidth.value = Math.min(RAIL_MAX_WIDTH, Math.max(RAIL_MIN_WIDTH, wanted))
}

// The rail only ever collapses to icons on desktop; below md the drawer always
// shows full labels, so the collapsed metrics must not apply there.
const railState = computed(() =>
  !isMobile.value && collapsed.value ? 'collapsed' : 'expanded',
)

function toggleSidebar() {
  if (isMobile.value) {
    mobileOpen.value = !mobileOpen.value
    return
  }

  collapsed.value = !collapsed.value
  localStorage.setItem(SIDEBAR_STATE_KEY, collapsed.value ? 'collapsed' : 'expanded')
}

function closeMobileSidebar() {
  mobileOpen.value = false
}

/* ── Breadcrumbs ────────────────────────────────────────────── */

const activeNav = computed(() =>
  navItems.value.find((item) => item.routeName === route.name),
)

const breadcrumbs = computed(() =>
  activeNav.value ? [t(activeNav.value.labelKey)] : [],
)

/* ── Behaviour ──────────────────────────────────────────────── */

function switchLang(code: string) {
  locale.value = code
  localStorage.setItem('locale', code)
  document.documentElement.lang = code
  langOpen.value = false
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}

function closeLang(event: MouseEvent) {
  if (!(event.target as HTMLElement).closest('.lang-wrapper')) langOpen.value = false
}

function handleKeydown(event: KeyboardEvent) {
  // The panel uses ctrl/cmd + b, and so does this rail.
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'b') {
    event.preventDefault()
    toggleSidebar()
  }
}

function syncViewport(event: MediaQueryList | MediaQueryListEvent) {
  isMobile.value = event.matches
  if (!event.matches) mobileOpen.value = false
  // The drawer drops the rail's outer gutter, so the width changes with it.
  measureRail()
}

// A drawer left open would hide the page the visitor just asked for.
watch(() => route.fullPath, closeMobileSidebar)

onMounted(() => {
  narrowViewport.addEventListener('change', syncViewport)
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('click', closeLang)
  measureRail()
})

// Labels change with the language, and the menu changes with the role.
watch([locale, navItems], measureRail, { flush: 'post' })

onUnmounted(() => {
  narrowViewport.removeEventListener('change', syncViewport)
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('click', closeLang)
})
</script>

<template>
  <div
    class="app-shell"
    :data-state="railState"
    :data-mobile-open="mobileOpen ? 'true' : 'false'"
    :style="railStyle"
  >
    <div v-if="isMobile && mobileOpen" class="scrim" @click="closeMobileSidebar" />

    <!-- Reserves the fixed rail's width in the flex flow. -->
    <div class="sidebar-gap" aria-hidden="true" />

    <aside class="sidebar">
      <div class="sidebar-panel">
        <div class="sidebar-header">
          <button
            type="button"
            class="rail-toggle"
            :aria-expanded="railState === 'expanded'"
            :aria-label="railState === 'expanded' ? t('sidebar.collapse') : t('sidebar.expand')"
            @click="toggleSidebar"
          >
            <span class="brand-mark"><AppIcon name="brand" /></span>
            <span class="brand-text">
              <span class="brand-name">{{ t('nav.brand') }}</span>
              <span class="brand-user">{{ auth.user?.name }}</span>
            </span>
          </button>
        </div>

        <nav class="sidebar-content" :aria-label="t('nav.brand')">
          <ul class="nav-list">
            <li v-for="item in navItems" :key="item.routeName">
              <router-link
                :to="{ name: item.routeName }"
                class="nav-item"
                :class="{ active: route.name === item.routeName }"
                :title="railState === 'collapsed' ? t(item.labelKey) : undefined"
                @click="closeMobileSidebar"
              >
                <AppIcon :name="item.icon" />
                <span class="nav-label">{{ t(item.labelKey) }}</span>
              </router-link>
            </li>
          </ul>
        </nav>

        <div class="sidebar-footer">
          <div class="lang-wrapper">
            <button
              type="button"
              class="nav-item"
              :title="railState === 'collapsed' ? LOCALES[locale] : undefined"
              :aria-expanded="langOpen"
              @click.stop="langOpen = !langOpen"
            >
              <AppIcon name="languages" />
              <span class="nav-label">{{ LOCALES[locale] || 'English' }}</span>
            </button>

            <Transition name="drop">
              <div v-if="langOpen" class="dropdown">
                <button
                  v-for="(name, code) in LOCALES"
                  :key="code"
                  type="button"
                  class="dropdown-item"
                  :class="{ active: code === locale }"
                  @click="switchLang(code)"
                >
                  <span>{{ name }}</span>
                  <AppIcon v-if="code === locale" name="check" />
                </button>
              </div>
            </Transition>
          </div>

          <button
            type="button"
            class="nav-item"
            :title="railState === 'collapsed' ? t('auth.sign_out') : undefined"
            @click="handleLogout"
          >
            <AppIcon name="log-out" />
            <span class="nav-label">{{ t('auth.sign_out') }}</span>
          </button>
        </div>
      </div>
    </aside>

    <!-- Off-screen ruler for the rail width: the same rows, drawn at their
         natural width, parked out of sight and measured on mount. -->
    <div ref="railRuler" class="rail-ruler" aria-hidden="true">
      <span v-for="row in railRulerRows" :key="row.key" class="nav-item">
        <AppIcon :name="row.icon" />
        <span class="nav-label">{{ row.label }}</span>
      </span>
    </div>

    <main class="sidebar-inset">
      <header class="mobile-bar">
        <button
          type="button"
          class="trigger"
          :aria-label="t('sidebar.toggle')"
          @click="toggleSidebar"
        >
          <AppIcon name="menu" />
        </button>
        <nav v-if="breadcrumbs.length" class="breadcrumbs" aria-label="Breadcrumb">
          <ol>
            <li v-for="(crumb, index) in breadcrumbs" :key="index">
              <span class="crumb">{{ crumb }}</span>
            </li>
          </ol>
        </nav>
      </header>

      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
  background: var(--background);
  color: var(--foreground);
}

/* ── Rail ───────────────────────────────────────────────────── */

/* Holds the rail's slot in the flex flow so the content card keeps its width
   while the fixed panel animates underneath. */
.sidebar-gap {
  flex-shrink: 0;
  width: var(--sidebar-width);
  transition: width 300ms var(--ease-sidebar);
}

.app-shell[data-state='collapsed'] .sidebar-gap {
  width: calc(var(--sidebar-width-icon) + var(--sidebar-gutter) * 2);
}

.sidebar {
  position: fixed;
  top: 0;
  bottom: 0;
  left: 0;
  z-index: 40;
  display: flex;
  width: var(--sidebar-width);
  padding: var(--sidebar-gutter);
  transition: width 300ms var(--ease-sidebar);
}

.app-shell[data-state='collapsed'] .sidebar {
  width: calc(var(--sidebar-width-icon) + var(--sidebar-gutter) * 2);
}

/*
 * The rail-width ruler. Parked off to the left so it can be measured without
 * the clip the real rows sit under: `max-content` makes every row report the
 * width its own label needs, whatever the language.
 */
.rail-ruler {
  position: absolute;
  top: 0;
  left: -9999px;
  display: flex;
  flex-direction: column;
  visibility: hidden;
  pointer-events: none;
}

.rail-ruler .nav-item {
  width: max-content;
  height: 2rem;
}

.sidebar-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  /* The collapsed language menu opens past the rail's right edge. */
  overflow: visible;
  border-radius: 0.75rem;
  background: var(--sidebar-background);
  color: var(--sidebar-foreground);
}

.sidebar-header {
  display: flex;
  flex-direction: column;
  /* No bottom padding: the nav's own top padding supplies the brand-to-nav gap
     so it matches the gap between menu items exactly. */
  padding: 0.5rem 0.5rem 0;
}

.rail-toggle {
  display: flex;
  align-items: center;
  /* Kept tight so the 10rem rail still fits the product name. */
  gap: 0.375rem;
  width: 100%;
  height: 2rem;
  padding: 0;
  overflow: hidden;
  border: 0;
  border-radius: 0.375rem;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color 150ms var(--ease-sidebar);
}

.rail-toggle:hover {
  background: var(--sidebar-accent);
}

.rail-toggle:focus-visible,
.nav-item:focus-visible,
.trigger:focus-visible {
  outline: 2px solid var(--sidebar-ring);
  outline-offset: 2px;
}

.app-shell[data-state='collapsed'] .rail-toggle {
  width: 2rem;
}

.brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 2rem;
  height: 2rem;
  border-radius: 0.375rem;
  background: var(--sidebar-brand);
  color: var(--sidebar-brand-foreground);
}

.brand-mark .app-icon {
  width: 1.125rem;
  height: 1.125rem;
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.15;
  transition: opacity 150ms var(--ease-sidebar);
}

.app-shell[data-state='collapsed'] .brand-text {
  opacity: 0;
}

.brand-name,
.brand-user {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.brand-name {
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.brand-user {
  font-size: 0.6875rem;
  opacity: 0.75;
}

/* ── Navigation ─────────────────────────────────────────────── */

.sidebar-content {
  flex: 1;
  min-height: 0;
  padding: var(--sidebar-item-gap) 0.5rem 0.5rem;
  overflow-x: hidden;
  overflow-y: auto;
}

.app-shell[data-state='collapsed'] .sidebar-content {
  overflow: hidden;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: var(--sidebar-item-gap);
  margin: 0;
  padding: 0;
  list-style: none;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  height: 2rem;
  padding: 0.5rem;
  /* Clips the label to nothing as the rail narrows. */
  overflow: hidden;
  border: 0;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--sidebar-foreground);
  font-family: inherit;
  font-size: 0.875rem;
  font-weight: 500;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
  transition:
    width 300ms var(--ease-sidebar),
    background-color 150ms var(--ease-sidebar),
    color 150ms var(--ease-sidebar),
    box-shadow 150ms var(--ease-sidebar);
}

.nav-item:hover {
  background: var(--sidebar-accent);
  color: var(--sidebar-accent-foreground);
}

.nav-item.active {
  background-image: linear-gradient(to right, var(--sidebar-primary), var(--sidebar-ring));
  color: var(--sidebar-primary-foreground);
  font-weight: 600;
  box-shadow: 0 4px 10px -2px color-mix(in srgb, var(--sidebar-primary) 45%, transparent);
}

.nav-item.active:hover {
  filter: brightness(1.08);
}

.app-shell[data-state='collapsed'] .nav-item {
  width: 2rem;
}

.nav-label {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.sidebar-footer {
  display: flex;
  flex-direction: column;
  gap: var(--sidebar-item-gap);
  padding: 0.5rem;
}

.lang-wrapper {
  position: relative;
}

.dropdown {
  position: absolute;
  left: 0;
  bottom: calc(100% + 0.25rem);
  z-index: 50;
  width: 100%;
  padding: 0.25rem;
  border: 1px solid var(--sidebar-border);
  border-radius: 0.5rem;
  background: var(--sidebar-background);
  box-shadow: 0 18px 40px -14px hsl(258 45% 6% / 0.55);
}

.app-shell[data-state='collapsed'] .dropdown {
  bottom: 0;
  left: calc(100% + 0.5rem);
  width: auto;
  min-width: 9rem;
}

.dropdown-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  width: 100%;
  padding: 0.4rem 0.5rem;
  border: 0;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--sidebar-foreground);
  font-family: inherit;
  font-size: 0.8125rem;
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 150ms var(--ease-sidebar), color 150ms var(--ease-sidebar);
}

.dropdown-item:hover {
  background: var(--sidebar-accent);
  color: var(--sidebar-accent-foreground);
}

.dropdown-item.active {
  color: var(--sidebar-primary);
  font-weight: 600;
}

.drop-enter-active,
.drop-leave-active {
  transition: opacity 120ms ease, transform 120ms ease;
}

.drop-enter-from,
.drop-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

/* ── Content card ───────────────────────────────────────────── */

.sidebar-inset {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  margin: var(--sidebar-gutter);
  margin-left: 0;
  border-radius: 0.75rem;
  background: var(--card);
  color: var(--card-foreground);
  box-shadow: 0 1px 2px 0 hsl(258 45% 6% / 0.06);
  /* `clip` rather than `hidden`: it contains overflowing pages without
     becoming a scroll container, so sticky table headers keep working. */
  overflow-x: clip;
}

.mobile-bar {
  display: none;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
  height: 4rem;
  padding: 0 1.5rem;
  border-bottom: 1px solid var(--border);
  background: var(--muted);
}

.trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  margin-left: -0.25rem;
  padding: 0;
  border: 0;
  border-radius: 0.375rem;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.trigger:hover {
  background: var(--accent);
}

.breadcrumbs ol {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 0.875rem;
}

.crumb {
  font-weight: 500;
}

/* ── Mobile drawer ──────────────────────────────────────────── */

.scrim {
  position: fixed;
  inset: 0;
  z-index: 30;
  background: hsl(258 45% 6% / 0.5);
}

@media (max-width: 767px) {
  .sidebar-gap {
    display: none;
  }

  .sidebar {
    /* Hugs the same measured width as the rail, capped for the phone. */
    width: min(var(--sidebar-width), 85vw);
    padding: 0;
    transform: translateX(-100%);
    transition: transform 300ms var(--ease-sidebar);
  }

  .app-shell[data-mobile-open='true'] .sidebar {
    transform: translateX(0);
  }

  .sidebar-panel {
    border-radius: 0;
  }

  /* The card loses its inset frame on small screens. */
  .sidebar-inset {
    margin: 0;
    border-radius: 0;
    box-shadow: none;
  }

  .mobile-bar {
    display: flex;
  }
}
</style>
