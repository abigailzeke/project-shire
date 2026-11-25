<script setup lang="ts">
// Claude Code's own widget: the three things the agent can't work without
// at the top, then its sessions and what each started, and its jobs.
import { computed } from "vue";
import { sections, toneOf, word, type Row } from "../model";
import { open } from "../store";
import type { Plugin } from "../types";
import ItemRow from "./ItemRow.vue";

const VITAL = ["agent", "remote-control", "anthropic"];
const props = defineProps<{ plugin: Plugin; rows: Row[] }>();
const vital = computed(() => VITAL.flatMap((key) => props.rows.filter((r) => r.key === key)));
const rest = computed(() => sections(props.rows.filter((r) => !VITAL.includes(r.key))));
</script>

<template>
  <div v-if="vital.length" class="ess">
    <button
      v-for="row in vital" :key="row.key" type="button" class="ess-chip" :class="toneOf(row)"
      @click="open({ kind: 'item', plugin: plugin.id, path: row.path })"
    >
      <span class="dot" aria-hidden="true"></span>
      <span class="txt"><span class="nm">{{ row.name }}</span><span class="st">{{ word(row) }}</span></span>
    </button>
  </div>
  <template v-for="section in rest" :key="section.title ?? ''">
    <div v-if="section.title" class="label">{{ section.title }}</div>
    <div class="items">
      <ItemRow v-for="row in section.rows" :key="row.key" :plugin="plugin" :row="row" />
    </div>
  </template>
</template>
