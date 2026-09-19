<script setup lang="ts">
/**
 * The shell's icon set.
 *
 * These are the inner shapes of the matching Lucide glyphs (ISC licensed,
 * https://lucide.dev), kept inline so the interface can share CerebrumKit's
 * iconography without pulling in an icon package. Every entry draws inside a
 * 24x24 viewBox and uses `currentColor`, so size and colour come from CSS.
 */
const ICONS: Record<string, string> = {
  chat:
    '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
  'folder-kanban':
    '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>' +
    '<path d="M8 10v4"/><path d="M12 10v2"/><path d="M16 10v6"/>',
  database:
    '<ellipse cx="12" cy="5" rx="9" ry="3"/>' +
    '<path d="M3 5V19A9 3 0 0 0 21 19V5"/>' +
    '<path d="M3 12A9 3 0 0 0 21 12"/>',
  sparkles:
    '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/>' +
    '<path d="M20 2v4"/><path d="M22 4h-4"/><circle cx="4" cy="20" r="2"/>',
  wrench:
    '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.106-3.105c.32-.322.863-.22.983.218a6 6 0 0 1-8.259 7.057l-7.91 7.91a1 1 0 0 1-2.999-3l7.91-7.91a6 6 0 0 1 7.057-8.259c.438.12.54.662.219.984z"/>',
  users:
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>' +
    '<path d="M16 3.128a4 4 0 0 1 0 7.744"/>' +
    '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/>' +
    '<circle cx="9" cy="7" r="4"/>',
  inbox:
    '<path d="M22 12h-6l-2 3h-4l-2-3H2"/>' +
    '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  'log-out':
    '<path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>' +
    '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>',
  'panel-left':
    '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
  // The mobile bar's sidebar toggle: three bars, the shape a phone reads as
  // "this opens the menu".
  menu:
    '<path d="M4 12h16"/><path d="M4 6h16"/><path d="M4 18h16"/>',
  languages:
    '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/>' +
    '<path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  search:
    '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  'sliders-horizontal':
    '<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/>' +
    '<path d="M21 20h-5"/><path d="M12 20H3"/>' +
    '<path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
  'x-circle':
    '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
  'alert-circle':
    '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  'plus-circle':
    '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/><path d="M12 8v8"/>',
  copy:
    '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>' +
    '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  layers:
    '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z"/>' +
    '<path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>' +
    '<path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
  // The documentation entry: an open book.
  'book-open':
    '<path d="M12 7v14"/>' +
    '<path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
  // Table of contents toggle on the docs page.
  list:
    '<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/>' +
    '<path d="M8 12h13"/><path d="M8 18h13"/><path d="M8 6h13"/>',
  'chevron-down': '<path d="m6 9 6 6 6-6"/>',
  'arrow-up': '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
  // The app mark: a brain, which is what the name promises. It is Lucide's
  // brain minus the six short surface ticks, which turn to mush at the 16px
  // favicon size; the two lobes and the inner fold still read as a brain.
  brand:
    '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>' +
    '<path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>' +
    '<path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>',
}

defineProps<{ name: string }>()
</script>

<template>
  <svg
    class="app-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
    v-html="ICONS[name] ?? ''"
  />
</template>

<style scoped>
.app-icon {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
  display: block;
}
</style>
