<script setup lang="ts">
// One tile in the snapshot. It opens to the item's details.
import { computed } from "vue";
import { series, type TileData } from "../model";
import { open, shire } from "../store";
import Avail from "./Avail.vue";
import Spark from "./Spark.vue";

const props = defineProps<{ tile: TileData }>();
const row = computed(() => props.tile.row);
const numeric = computed(() => typeof row.value.value === "number");
const points = computed(() =>
  props.tile.plugin.history.includes(row.value.key) ? shire.history[props.tile.plugin.id] ?? [] : []);
const show = () => open({ kind: "item", plugin: props.tile.plugin.id, path: row.value.path });
</script>

<template>
  <article
    class="kpi" role="button" tabindex="0"
    :class="[tile.colour ? `tone-${tile.colour}` : '', { down: row.state === 'bad', amber: row.state === 'warn' }]"
    @click="show" @keydown.enter="show"
  >
    <h3>{{ row.name }}</h3>
    <div class="val" :class="{ words: !numeric }">{{ row.value ?? "—" }}<small v-if="numeric && row.unit">{{ row.unit }}</small></div>
    <div class="ksub">{{ row.mine ?? row.note ?? "" }}</div>
    <div v-if="points.length" class="spark-wrap">
      <Spark v-if="numeric" :points="series(points, row.key)" :unit="row.unit" />
      <Avail v-else compact :points="points" :name="row.key" />
    </div>
  </article>
</template>
