<script setup lang="ts">
import OfflineBanner from './components/OfflineBanner.vue'
import DemoBanner from './demo/DemoBanner.vue'
</script>

<template>
  <DemoBanner />
  <OfflineBanner />
  <router-view />
</template>
