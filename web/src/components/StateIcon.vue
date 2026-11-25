<script setup lang="ts">
// A status never rides on colour alone: each has its own shape.
defineProps<{ tone: "good" | "warn" | "crit" | "off" }>();
</script>

<template>
  <svg v-if="tone === 'good'" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" class="f" /><path d="M4.9 8.2l2.1 2.1 4.2-4.5" class="s" /></svg>
  <svg v-else-if="tone === 'warn'" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5l7 12.4H1z" class="f" /><path d="M8 6.2v3.4M8 11.7v.1" class="s" /></svg>
  <svg v-else-if="tone === 'crit'" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" class="f" /><path d="M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8" class="s" /></svg>
  <svg v-else viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.6" class="o" /></svg>
</template>
