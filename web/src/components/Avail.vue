<script setup lang="ts">
// 24 hours of good or not, half an hour a bar.
import { computed } from "vue";
import { availability, clock, type Point } from "../model";
import { shire } from "../store";

const props = defineProps<{ points: Point[]; name: string; title?: string; compact?: boolean }>();
const found = computed(() => availability(props.points, props.name, shire.now));
const percent = computed(() => {
  const p = found.value.percent;
  return p === null ? "starts now" : p >= 99.95 ? "100%" : `${p.toFixed(1)}%`;
});
const WORD = { good: "good the whole time", warn: "good some of the time", crit: "not good", none: "no record" };
</script>

<template>
  <div :class="compact ? 'avail-mini' : 'avail'">
    <div v-if="!compact" class="avail-top"><span>{{ title }}</span><b>{{ percent }}</b></div>
    <div class="bars" role="img" :aria-label="`${title ?? 'The last 24 hours'}: good ${percent} of the time`">
      <i v-for="slot in found.slots" :key="slot.from" :class="slot.kind" :title="`${clock(slot.from)} · ${WORD[slot.kind]}`"></i>
    </div>
    <div v-if="!compact" class="avail-cap"><span>24 h ago</span><span>now</span></div>
  </div>
</template>
