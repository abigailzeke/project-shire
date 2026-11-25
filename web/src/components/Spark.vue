<script setup lang="ts">
// A number's last 24 hours as a line. Where nothing was read for a while,
// the line has a gap.
import { computed } from "vue";

const props = defineProps<{ points: { t: number; v: number }[]; unit?: string }>();
const W = 200, H = 34, PAD = 3, GAP = 900;

const drawn = computed(() => {
  const pts = props.points;
  if (pts.length < 2) return null;
  const t0 = pts[0].t, t1 = Math.max(pts[pts.length - 1].t, t0 + 1);
  let lo = props.unit === "%" ? 0 : Math.min(...pts.map((p) => p.v));
  let hi = props.unit === "%" ? 100 : Math.max(...pts.map((p) => p.v));
  if (hi - lo < 1e-9) [lo, hi] = [lo - 1, hi + 1];
  const x = (t: number) => (PAD + ((t - t0) / (t1 - t0)) * (W - 2 * PAD)).toFixed(1);
  const y = (v: number) => (H - PAD - ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * (H - 2 * PAD)).toFixed(1);
  let line = "", area = "", run: { t: number; v: number }[] = [];
  const close = () => {
    if (run.length > 1) area += `M${x(run[0].t)},${H - 1} ${run.map((p) => `L${x(p.t)},${y(p.v)}`).join(" ")} L${x(run[run.length - 1].t)},${H - 1} Z `;
    run = [];
  };
  pts.forEach((p, i) => {
    const gap = i > 0 && p.t - pts[i - 1].t > GAP;
    if (gap) close();
    line += `${i === 0 || gap ? "M" : "L"}${x(p.t)},${y(p.v)} `;
    run.push(p);
  });
  close();
  return { line, area };
});
</script>

<template>
  <svg class="spark" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none" role="img" aria-label="The last 24 hours">
    <line class="base" x1="0" :x2="W" :y1="H - 1" :y2="H - 1" />
    <template v-if="drawn">
      <path class="area" :d="drawn.area" />
      <path class="path" :d="drawn.line" />
    </template>
  </svg>
</template>
