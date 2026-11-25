<script setup lang="ts">
// One row that opens: a name, a line under it, and where it stands.
import { ref } from "vue";
import { toneOf, word, type Row } from "../model";
import type { Plugin } from "../types";
import ItemDetails from "./ItemDetails.vue";
import Pill from "./Pill.vue";

defineProps<{ plugin: Plugin; row: Row }>();
const isOpen = ref(false);
</script>

<template>
  <details class="item" @toggle="isOpen = ($event.target as HTMLDetailsElement).open">
    <summary>
      <div class="txt">
        <div class="nm">{{ row.name }}</div>
        <div v-if="row.original" class="orig">{{ row.original }}</div>
        <div v-if="row.mine || row.note" class="sub">{{ row.mine ?? row.note }}</div>
      </div>
      <span v-if="row.watched" class="eye" role="img" aria-label="You watch this" title="You watch this"></span>
      <Pill v-if="row.state" :tone="toneOf(row)" :text="word(row)" />
      <span v-else-if="word(row)" class="r">{{ word(row) }}</span>
      <span class="chev" aria-hidden="true"></span>
    </summary>
    <ItemDetails v-if="isOpen" :plugin="plugin" :row="row" />
  </details>
</template>
