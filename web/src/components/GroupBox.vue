<script setup lang="ts">
// A group: a box with a name and a colour, holding the widgets you put in
// it, in your order. It's only for the eye. Its name folds it, and a plugin
// that's switched off takes no room in it.
import { computed } from "vue";
import type { Box } from "../model";
import { fold, folded, open } from "../store";
import PluginWidget from "./PluginWidget.vue";

const props = defineProps<{ box: Box }>();
const foldId = computed(() => `group:${props.box.group.id || "none"}`);
const shut = computed(() => folded(foldId.value));
const on = computed(() => props.box.plugins.filter((p) => p.enabled));
</script>

<template>
  <div class="sect" :class="box.group.colour ? `tone-${box.group.colour}` : ''">
    <header class="sh">
      <div class="txt">
        <h2>
          <button type="button" class="fold" :aria-expanded="!shut" @click="fold(foldId, !shut)">
            {{ box.group.name }}<span class="chev" aria-hidden="true"></span>
          </button>
        </h2>
        <p v-if="shut">{{ on.length }} {{ on.length === 1 ? "widget" : "widgets" }}, folded away</p>
        <p v-else-if="box.group.note">{{ box.group.note }}</p>
      </div>
      <button
        v-if="!box.other" type="button" class="icon-btn small" :aria-label="`Options for ${box.group.name}`"
        @click="open({ kind: 'group', group: box.group.id })"
      >
        <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="4.5" cy="10" r="1.6" fill="currentColor" /><circle cx="10" cy="10" r="1.6" fill="currentColor" /><circle cx="15.5" cy="10" r="1.6" fill="currentColor" /></svg>
      </button>
    </header>
    <template v-if="!shut">
      <div v-if="on.length" class="grid">
        <PluginWidget v-for="plugin in on" :key="plugin.id" :plugin="plugin" />
      </div>
      <p v-else class="empty">
        {{ box.plugins.length ? "Everything in this group is switched off." : "Nothing in this group yet. Move a plugin here from its menu." }}
      </p>
    </template>
  </div>
</template>
