<script setup lang="ts">
/**
 * The Documentation page: the text of `src/docs`, in the interface language,
 * with a grouped table of contents beside it.
 *
 * The whole document is rendered at once rather than one section at a time, so
 * the browser's own find-in-page and the page's search box both work over the
 * full text. The rail is a set of in-page anchors, and the section being read
 * is highlighted by watching which headings are on screen.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '../../components/AppIcon.vue'
import { docsFor } from '../../docs'
import { renderMarkdown } from '../../utils/markdown'

const { t, locale } = useI18n()

// The text follows the interface language. Markdown is rendered once per
// language rather than once per keystroke: the text is static, and re-rendering
// twenty-one sections while someone types in the search box would be waste.
const docs = computed(() => docsFor(locale.value))

const sections = computed(() =>
  docs.value.sections.map((section) => ({
    ...section,
    html: renderMarkdown(section.body),
  })),
)

const query = ref('')
const activeId = ref(sections.value[0]?.id ?? '')
const tocOpen = ref(false)
const showTop = ref(false)

// Which cluster a section sits in, for the eyebrow above its heading.
const groupLabelById = computed(() => {
  const labels = new Map<string, string>()
  for (const group of docs.value.groups) {
    for (const id of group.ids) labels.set(id, group.label)
  }
  return labels
})

const visible = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return sections.value
  return sections.value.filter(
    (section) =>
      section.title.toLowerCase().includes(needle) ||
      section.body.toLowerCase().includes(needle),
  )
})

const tocGroups = computed(() => {
  const byId = new Map(visible.value.map((section) => [section.id, section]))
  const groups = docs.value.groups
    .map((group) => ({
      label: group.label,
      sections: group.ids
        .map((id) => byId.get(id))
        .filter((section): section is (typeof sections.value)[number] => Boolean(section)),
    }))
    .filter((group) => group.sections.length > 0)

  // A section no group names still has to be reachable from the rail.
  const grouped = new Set(docs.value.groups.flatMap((group) => group.ids))
  const orphans = visible.value.filter((section) => !grouped.has(section.id))
  if (orphans.length) groups.push({ label: t('admin.docs.more'), sections: orphans })
  return groups
})

function goTo(id: string) {
  tocOpen.value = false
  activeId.value = id
  document.getElementById(`doc-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function scrollTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

/* ── Which section is on screen ─────────────────────────────────
 *
 * The heading nearest the top of the viewport is the one being read, so the
 * observer keeps a running note of what is visible and the rail picks the first
 * of those in document order. A plain "last one to intersect" would flicker
 * between two headings while a long section scrolls past.
 */
let observer: IntersectionObserver | null = null
const onScreen = ref<Set<string>>(new Set())

function observeSections() {
  observer?.disconnect()
  onScreen.value = new Set()
  observer = new IntersectionObserver(
    (entries) => {
      const next = new Set(onScreen.value)
      for (const entry of entries) {
        const id = entry.target.id.replace(/^doc-/, '')
        if (entry.isIntersecting) next.add(id)
        else next.delete(id)
      }
      onScreen.value = next
    },
    // The band is the top fifth of the screen: a heading counts as current
    // once it reaches the top, and stops counting once scrolled well past.
    { rootMargin: '-10% 0px -80% 0px', threshold: 0 },
  )
  for (const section of sections.value) {
    const el = document.getElementById(`doc-${section.id}`)
    if (el) observer.observe(el)
  }
}

watch(onScreen, (ids) => {
  const first = sections.value.find((section) => ids.has(section.id))
  if (first) activeId.value = first.id
})

// Re-observe after a filter changes which sections exist in the DOM.
watch(visible, () => {
  if (query.value.trim()) return
  requestAnimationFrame(observeSections)
})

// A language switch replaces every heading and paragraph, so the observer has
// to be rebuilt against the new DOM rather than left watching detached nodes.
watch(locale, async () => {
  await nextTick()
  activeId.value = sections.value[0]?.id ?? ''
  observeSections()
})

function onScroll() {
  showTop.value = window.scrollY > 500
}

onMounted(() => {
  observeSections()
  window.addEventListener('scroll', onScroll, { passive: true })
})

onBeforeUnmount(() => {
  observer?.disconnect()
  window.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <div class="admin-page docs-page">
    <header class="docs-hero">
      <span class="hero-eyebrow">
        <AppIcon name="book-open" />
        {{ t('nav.brand') }}
      </span>
      <h1>{{ t('admin.docs.title') }}</h1>
      <p class="hero-subtitle">{{ t('admin.docs.subtitle') }}</p>

      <label class="docs-search">
        <AppIcon name="search" />
        <input
          v-model="query"
          type="search"
          :placeholder="t('admin.docs.search_placeholder')"
          :aria-label="t('admin.docs.search_placeholder')"
        />
        <button
          v-if="query"
          type="button"
          class="search-clear"
          :aria-label="t('admin.docs.clear')"
          @click="query = ''"
        >
          <AppIcon name="x-circle" />
        </button>
      </label>
    </header>

    <div class="docs-layout">
      <nav class="docs-rail" :aria-label="t('admin.docs.contents')">
        <button
          type="button"
          class="rail-toggle"
          :aria-expanded="tocOpen"
          @click="tocOpen = !tocOpen"
        >
          <AppIcon name="list" />
          <span>{{ t('admin.docs.contents') }}</span>
          <AppIcon name="chevron-down" class="rail-chevron" :class="{ open: tocOpen }" />
        </button>

        <div class="rail-panel" :class="{ open: tocOpen }">
          <div v-for="group in tocGroups" :key="group.label" class="rail-group">
            <p class="rail-label">{{ group.label }}</p>
            <ul>
              <li v-for="section in group.sections" :key="section.id">
                <button
                  type="button"
                  class="rail-link"
                  :class="{ active: section.id === activeId }"
                  :aria-current="section.id === activeId ? 'true' : undefined"
                  @click="goTo(section.id)"
                >
                  {{ section.title }}
                </button>
              </li>
            </ul>
          </div>
        </div>
      </nav>

      <article class="docs-body">
        <p v-if="!visible.length" class="docs-empty">
          <AppIcon name="search" />
          {{ t('admin.docs.no_results') }}
        </p>

        <section
          v-for="section in visible"
          :id="`doc-${section.id}`"
          :key="section.id"
          class="doc-card"
        >
          <p class="doc-eyebrow">{{ groupLabelById.get(section.id) ?? t('admin.docs.more') }}</p>
          <h2>{{ section.title }}</h2>
          <!-- The text is authored in this repository, not supplied by a user. -->
          <div class="doc-content" v-html="section.html" />
        </section>
      </article>
    </div>

    <Transition name="fade">
      <button
        v-if="showTop"
        type="button"
        class="to-top"
        :aria-label="t('admin.docs.back_to_top')"
        @click="scrollTop"
      >
        <AppIcon name="arrow-up" />
      </button>
    </Transition>
  </div>
</template>

<style scoped>
.docs-page {
  max-width: 1240px;
  margin: 0 auto;
  /* The shell only supplies the outer inset frame, and this view does not
     import admin-crud.css, so the page owns its own breathing room. A
     reading page wants more than the 1.5rem the table screens use. */
  padding: 2.25rem 2.5rem 3.5rem;
}

/* ── Hero ─────────────────────────────────────────────────────
   A tinted panel rather than a bare heading: it gives the page a
   top, and it is where the search box belongs. */

.docs-hero {
  position: relative;
  overflow: hidden;
  margin-bottom: 1.75rem;
  padding: 2.25rem 2.4rem 2.15rem;
  border: 1px solid var(--border);
  border-radius: 16px;
  background:
    radial-gradient(105% 130% at 100% 0%, hsl(280 85% 96%) 0%, transparent 58%),
    linear-gradient(158deg, hsl(266 72% 98%) 0%, var(--card) 72%);
}

.docs-hero::after {
  content: '';
  position: absolute;
  top: -80px;
  right: -60px;
  width: 250px;
  height: 250px;
  border-radius: 50%;
  background: radial-gradient(circle, hsl(282 92% 88% / 0.5), transparent 70%);
  pointer-events: none;
}

.hero-eyebrow {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 1rem;
  padding: 0.32rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--card);
  color: var(--secondary-foreground);
  font-size: 0.7rem;
  font-weight: 750;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.docs-hero h1 {
  position: relative;
  margin: 0;
  color: var(--foreground);
  font-size: 2rem;
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.hero-subtitle {
  position: relative;
  max-width: 56ch;
  margin: 0.7rem 0 0;
  color: var(--muted-foreground);
  font-size: 0.95rem;
  line-height: 1.55;
}

.docs-search {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.55rem;
  max-width: 460px;
  min-height: 44px;
  margin-top: 1.75rem;
  padding: 0 0.95rem;
  border: 1px solid var(--input);
  border-radius: 10px;
  background: var(--card);
  color: var(--muted-foreground);
  box-shadow: 0 1px 2px hsl(258 45% 6% / 0.05);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.docs-search:focus-within {
  border-color: var(--ring);
  box-shadow: 0 0 0 3px hsl(276 80% 62% / 0.18);
}

.docs-search input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--foreground);
  font-family: inherit;
  font-size: 0.92rem;
}

/* The panel draws its own clear button, so the native one is suppressed. */
.docs-search input::-webkit-search-cancel-button {
  display: none;
}

.search-clear {
  display: inline-flex;
  padding: 0;
  border: 0;
  background: none;
  color: var(--muted-foreground);
  cursor: pointer;
}

.search-clear:hover {
  color: var(--foreground);
}

/* ── Layout ─────────────────────────────────────────────────── */

.docs-layout {
  display: grid;
  grid-template-columns: 268px minmax(0, 1fr);
  gap: 1.75rem;
  align-items: start;
}

/* ── Contents rail ────────────────────────────────────────────── */

.docs-rail {
  position: sticky;
  top: 1rem;
  max-height: calc(100vh - 2.5rem);
  overflow-y: auto;
  padding: 1.15rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--card);
  box-shadow: 0 1px 2px hsl(258 45% 6% / 0.04);
}

/* The rail is always open on desktop; the toggle only appears on narrow
   screens, where a full-height column of links is not affordable. */
.rail-toggle {
  display: none;
}

.rail-group + .rail-group {
  margin-top: 1.1rem;
}

.rail-label {
  margin: 0 0 0.5rem;
  padding: 0 0.6rem;
  color: var(--muted-foreground);
  font-size: 0.67rem;
  font-weight: 750;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

.docs-rail ul {
  display: grid;
  gap: 1px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.rail-link {
  position: relative;
  display: block;
  width: 100%;
  padding: 0.45rem 0.6rem;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--muted-foreground);
  font-family: inherit;
  font-size: 0.845rem;
  line-height: 1.35;
  text-align: left;
  cursor: pointer;
  transition: background 0.14s ease, color 0.14s ease;
}

.rail-link:hover {
  background: var(--muted);
  color: var(--foreground);
}

.rail-link.active {
  background: var(--accent);
  color: var(--accent-foreground);
  font-weight: 650;
}

.rail-link.active::before {
  content: '';
  position: absolute;
  top: 0.35rem;
  bottom: 0.35rem;
  left: 0;
  width: 2px;
  border-radius: 2px;
  background: var(--primary);
}

/* ── Document ───────────────────────────────────────────────── */

.docs-body {
  display: grid;
  /* A grid track sized `auto` takes its minimum from the items' min-content,
     and a grid item's `min-width: auto` does the same. A wide table or code
     block then pushes the whole column past the viewport, where the shell's
     `overflow-x: clip` cuts it off with no way to scroll back. Pinning the
     track to minmax(0, 1fr) and zeroing the card's minimum keeps the column
     inside the frame and lets the scroll containers inside handle the rest. */
  grid-template-columns: minmax(0, 1fr);
  gap: 1.35rem;
  min-width: 0;
}

.doc-card {
  min-width: 0;
  padding: 2.1rem 2.4rem 2.4rem;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--card);
  box-shadow: 0 1px 2px hsl(258 45% 6% / 0.04);
  /* Clears the top of the window when an anchor is jumped to. */
  scroll-margin-top: 1.25rem;
}

.doc-eyebrow {
  margin: 0 0 0.6rem;
  color: var(--primary);
  font-size: 0.67rem;
  font-weight: 750;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

.doc-card > h2 {
  margin: 0 0 1.3rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border);
  color: var(--foreground);
  font-size: 1.3rem;
  letter-spacing: -0.01em;
}

.docs-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  padding: 3rem 1rem;
  border: 1px dashed var(--border);
  border-radius: 14px;
  background: var(--card);
  color: var(--muted-foreground);
  font-size: 0.9rem;
}

/* ── Rendered markdown ──────────────────────────────────────────
   Scoped styles cannot reach v-html content, so these reach in with
   `:deep`. Prose is capped at a readable measure; tables and code
   blocks keep the card's full width because they carry their own
   structure. */

:deep(.doc-content) {
  /* Long paths and identifiers with no spaces still have to wrap. */
  overflow-wrap: break-word;
  color: hsl(258 22% 28%);
  font-size: 0.92rem;
  line-height: 1.7;
}

:deep(.doc-content > p),
:deep(.doc-content > ul),
:deep(.doc-content > ol),
:deep(.doc-content > h3),
:deep(.doc-content > h4),
:deep(.doc-content > blockquote) {
  max-width: 80ch;
}

:deep(.doc-content > *:first-child) {
  margin-top: 0;
}

:deep(.doc-content p) {
  margin: 0.9rem 0;
}

:deep(.doc-content h3) {
  margin: 2.2rem 0 0.8rem;
  color: var(--foreground);
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: -0.005em;
}

:deep(.doc-content h4) {
  margin: 1.6rem 0 0.65rem;
  color: var(--foreground);
  font-size: 0.92rem;
  font-weight: 700;
}

:deep(.doc-content ul),
:deep(.doc-content ol) {
  margin: 0.9rem 0;
  padding-left: 1.45rem;
}

:deep(.doc-content li) {
  margin: 0.4rem 0;
}

:deep(.doc-content li::marker) {
  color: var(--primary);
  font-weight: 700;
}

:deep(.doc-content strong) {
  color: var(--foreground);
  font-weight: 700;
}

:deep(.doc-content a) {
  border-bottom: 1px solid hsl(264 82% 56% / 0.32);
  color: var(--primary);
  text-decoration: none;
}

:deep(.doc-content a:hover) {
  border-bottom-color: var(--primary);
}
/* The author portrait sits above the bio. A fixed width keeps it a portrait
   rather than a full-bleed image, and the shadow lifts it off the card. */
:deep(.doc-content img) {
  display: block;
  width: 150px;
  height: auto;
  margin: 1.1rem 0 1.4rem;
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 12px 26px -14px hsl(258 45% 6% / 0.45);
}

/* Inline code reads as a token, not as a highlighted word. */
:deep(.doc-content code) {
  padding: 0.12rem 0.4rem;
  border-radius: 6px;
  background: var(--secondary);
  color: var(--secondary-foreground);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.83em;
  font-weight: 500;
}

:deep(.doc-content pre) {
  margin: 1rem 0;
  padding: 0.95rem 1.1rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: hsl(258 36% 97.5%);
  overflow-x: auto;
}

:deep(.doc-content pre code) {
  padding: 0;
  background: transparent;
  color: hsl(258 25% 25%);
  font-size: 0.8rem;
  line-height: 1.65;
  font-weight: 400;
}

/* Blockquotes are the page's callouts - the security notes and warnings. */
:deep(.doc-content blockquote) {
  margin: 1.1rem 0;
  padding: 0.85rem 1.1rem;
  border: 1px solid hsl(276 62% 89%);
  border-left: 3px solid var(--primary);
  border-radius: 10px;
  background: hsl(276 74% 97.5%);
  color: hsl(266 45% 32%);
}

:deep(.doc-content blockquote p) {
  margin: 0;
}

:deep(.doc-content blockquote strong) {
  color: hsl(266 58% 26%);
}

:deep(.doc-content .md-table-wrap) {
  margin: 1.1rem 0;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow-x: auto;
}

:deep(.doc-content .md-data-table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.855rem;
}

:deep(.doc-content .md-data-table th),
:deep(.doc-content .md-data-table td) {
  padding: 0.6rem 0.85rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

:deep(.doc-content .md-data-table th) {
  background: var(--muted);
  color: var(--secondary-foreground);
  font-size: 0.69rem;
  font-weight: 750;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  white-space: nowrap;
}

:deep(.doc-content .md-data-table tbody tr:nth-child(even)) {
  background: hsl(258 36% 98.5%);
}

:deep(.doc-content .md-data-table tbody tr:last-child td) {
  border-bottom: 0;
}

/* ── Back to top ────────────────────────────────────────────── */

.to-top {
  position: fixed;
  right: 1.5rem;
  bottom: 1.5rem;
  z-index: 20;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--card);
  color: var(--secondary-foreground);
  box-shadow: 0 10px 24px -8px hsl(258 45% 6% / 0.4);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, transform 0.15s ease;
}

.to-top:hover {
  border-color: var(--primary);
  background: var(--primary);
  color: var(--primary-foreground);
  transform: translateY(-2px);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

/* ── Narrow screens ─────────────────────────────────────────── */

@media (max-width: 1000px) {
  .docs-page {
    padding: 2rem 1.75rem 3rem;
  }

  .docs-layout {
    grid-template-columns: minmax(0, 1fr);
    gap: 1.15rem;
  }

  .docs-rail {
    position: static;
    max-height: none;
    padding: 0.6rem 0.75rem;
  }

  .rail-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.5rem 0.6rem;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: var(--foreground);
    font-family: inherit;
    font-size: 0.9rem;
    font-weight: 650;
    cursor: pointer;
  }

  .rail-toggle:hover {
    background: var(--muted);
  }

  .rail-chevron {
    margin-left: auto;
    transition: transform 0.18s ease;
  }

  .rail-chevron.open {
    transform: rotate(180deg);
  }

  .rail-panel {
    display: none;
    padding: 0.5rem 0.35rem 0.35rem;
  }

  .rail-panel.open {
    display: block;
  }

  .rail-group + .rail-group {
    margin-top: 0.9rem;
  }
}

@media (max-width: 760px) {
  .docs-page {
    max-width: 100%;
    padding: 1.25rem 1.15rem 2.5rem;
  }

  .docs-hero {
    margin-bottom: 1.25rem;
    padding: 1.5rem 1.35rem 1.55rem;
  }

  .docs-hero h1 {
    font-size: 1.55rem;
  }

  .docs-search {
    max-width: none;
  }

  .doc-card {
    padding: 1.45rem 1.35rem 1.6rem;
  }
  :deep(.doc-content img) {
    width: 118px;
  }

  .to-top {
    right: 1rem;
    bottom: 1rem;
  }
}
</style>
