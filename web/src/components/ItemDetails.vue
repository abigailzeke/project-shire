<script setup lang="ts">
// What an item opens to: your line about it, its note, its last 24 hours,
// its details and its parts, and watch, rename and hide.
import { computed } from "vue";
import { series, valueText, watchPatch, type Row } from "../model";
import { choose, open, shire } from "../store";
import type { Plugin } from "../types";
import Avail from "./Avail.vue";
import ItemRow from "./ItemRow.vue";
import Spark from "./Spark.vue";

const props = defineProps<{ plugin: Plugin; row: Row }>();
const points = computed(() =>
  props.row.path.length === 1 && props.plugin.history.includes(props.row.key) ? shire.history[props.plugin.id] ?? [] : []);
const shownParts = computed(() => props.row.parts.filter((p) => !p.hidden));
const hiddenParts = computed(() => props.row.parts.filter((p) => p.hidden));
</script>

<template>
  <div class="more">
    <p v-if="row.mine" class="does">{{ row.mine }}</p>
    <p v-if="row.missing" class="fix"><b>Missing</b>You watch this, and it isn't there right now.</p>
    <p v-if="row.note" class="does" :class="{ dim: row.mine }">{{ row.note }}</p>

    <template v-if="points.length">
      <div v-if="typeof row.value === 'number'" class="avail">
        <div class="avail-top"><span>The last 24 hours</span><b>{{ valueText(row) }}</b></div>
        <Spark :points="series(points, row.key)" :unit="row.unit" />
        <div class="avail-cap"><span>24 h ago</span><span>now</span></div>
      </div>
      <Avail v-else :points="points" :name="row.key" title="The last 24 hours" />
    </template>

    <dl v-if="row.renamed || row.original || row.facts.length" class="facts">
      <template v-if="row.renamed"><dt>Its own name</dt><dd>{{ row.own }}</dd></template>
      <template v-if="row.original && row.original !== row.own"><dt>Original name</dt><dd class="m">{{ row.original }}</dd></template>
      <template v-for="[label, fact] in row.facts" :key="label">
        <dt>{{ label }}</dt><dd :class="{ m: fact.length > 32 }">{{ fact }}</dd>
      </template>
    </dl>

    <div v-if="shownParts.length" class="parts">
      <ItemRow v-for="part in shownParts" :key="part.key" :plugin="plugin" :row="part" />
    </div>
    <div v-for="part in hiddenParts" :key="part.key" class="mini">
      <div class="txt"><div class="nm">{{ part.name }}</div><div class="sub">Hidden</div></div>
      <button type="button" class="act" @click="choose(plugin.id, part.path, { hidden: null })">Show</button>
    </div>

    <div class="acts">
      <button type="button" class="act" @click="choose(plugin.id, row.path, watchPatch(plugin, row))">
        {{ row.watched ? "Stop watching" : "Watch" }}
      </button>
      <button type="button" class="act" @click="open({ kind: 'name-item', plugin: plugin.id, path: row.path })">Rename</button>
      <button type="button" class="act" @click="choose(plugin.id, row.path, { hidden: row.hidden ? null : true })">
        {{ row.hidden ? "Show" : "Hide" }}
      </button>
    </div>
  </div>
</template>
