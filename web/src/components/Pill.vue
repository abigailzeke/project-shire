<script setup lang="ts">
import type { Tone } from "../model";
import StateIcon from "./StateIcon.vue";

defineProps<{ tone: Tone; text: string }>();
</script>

<template>
  <span class="pill" :class="tone === 'off' ? 'n' : tone">
    <StateIcon v-if="tone !== 'off'" :tone="tone" />
    <span>{{ text }}</span>
  </span>
</template>
