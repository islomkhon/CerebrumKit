<script setup lang="ts">
import { IS_DEMO } from './mode'
</script>

<template>
  <div v-if="IS_DEMO" class="demo-bar">
    <span class="tag">Static demo</span>
    <span class="text">
      A snapshot of a seeded install, served as files from GitHub Pages. No model is
      connected, so a chat reply is canned; edits are not saved. Sign in with any address
      &mdash; one containing &ldquo;client&rdquo; opens the client panel.
    </span>
    <a class="link" href="https://github.com/islomkhon/CerebrumKit" target="_blank" rel="noopener">
      Source
    </a>
  </div>
</template>

<style scoped>
/* Sits above everything, including the offline banner, because it explains the
   whole page and has to be readable before anything else is trusted. */
.demo-bar {
  position: relative;
  z-index: 60;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  padding: 0.45rem 0.9rem;
  background: #312e81;
  color: #e0e7ff;
  font-size: 0.78rem;
  line-height: 1.4;
}
.tag {
  flex: none;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: #6366f1;
  color: #fff;
  font-weight: 600;
  letter-spacing: 0.01em;
}
.text {
  flex: 1 1 22rem;
  min-width: 0;
}
.link {
  flex: none;
  color: #c7d2fe;
  font-weight: 600;
  text-decoration: none;
}
.link:hover {
  color: #fff;
  text-decoration: underline;
}
</style>
