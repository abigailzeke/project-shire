<script setup lang="ts">
// The top of the page: one line that says whether anything needs you, a bar
// with a mark for each thing you watch, and, apart from the bar, the tiles
// the plugins give. The line speaks up only for what you watch.
import { computed } from "vue";
import { headline, needText, tiles, toneOf, watching } from "../model";
import { open } from "../store";
import type { Status } from "../types";
import StateIcon from "./StateIcon.vue";
import Tile from "./Tile.vue";

const props = defineProps<{ status: Status }>();
const watched = computed(() => watching(props.status));
const head = computed(() => headline(props.status.needs, watched.value.length));
const needs = computed(() => [...props.status.needs].sort((a, b) => Number(a.why === "warn") - Number(b.why === "warn")));
const allTiles = computed(() => tiles(props.status));
</script>

<template>
  <section class="snapshot" aria-labelledby="glance-title">
    <header class="sh"><div class="txt"><h2 id="glance-title">Everything at a glance</h2><p>Tap a tile for more.</p></div></header>
    <div class="banner" :class="head.tone">
      <div aria-live="polite">
        <div class="b-row">
          <div class="b-ic" :class="head.tone"><StateIcon :tone="head.tone" /></div>
          <div class="txt"><h2 class="b-title">{{ head.title }}</h2><p class="b-sub">{{ head.sub }}</p></div>
        </div>
        <ul v-if="needs.length" class="issues">
          <li v-for="need in needs" :key="`${need.plugin}/${need.path.join('/')}`" :class="need.why === 'warn' ? 'warn' : 'crit'">
            <StateIcon :tone="need.why === 'warn' ? 'warn' : 'crit'" />
            <button type="button" class="issue" @click="open({ kind: 'item', plugin: need.plugin, path: need.path })">{{ needText(need) }}</button>
          </li>
        </ul>
      </div>
      <div v-if="watched.length" class="watching">
        <div class="label">What you watch<span>One mark each. Tap a mark to open it.</span></div>
        <div class="score" role="img" :aria-label="head.sub">
          <i
            v-for="w in watched" :key="`${w.plugin.id}/${w.row.path.join('/')}`"
            :class="toneOf(w.row) === 'off' ? 'good' : toneOf(w.row)" :title="w.row.name"
            @click="open({ kind: 'item', plugin: w.plugin.id, path: w.row.path })"
          ></i>
        </div>
      </div>
      <div v-if="allTiles.length" class="now">
        <div class="label">Right now</div>
        <div class="kpis">
          <Tile v-for="tile in allTiles" :key="`${tile.plugin.id}/${tile.row.key}`" :tile="tile" />
        </div>
      </div>
    </div>
  </section>
</template>
