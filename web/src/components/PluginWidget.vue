<script setup lang="ts">
// The one standard widget. It shows any plugin from its output, as a list,
// numbers, gauges or a table, whichever its plugin.yaml asks for. Its name
// folds it.
import { computed, reactive } from "vue";
import { ago, every, rows as rowsOf, sections, valueText } from "../model";
import { choose, fold, folded, open, shire } from "../store";
import type { Plugin } from "../types";
import ClaudeCode from "./ClaudeCode.vue";
import ItemRow from "./ItemRow.vue";

const LIMIT = 8; // a long list shows this many until you ask for the rest

const props = defineProps<{ plugin: Plugin }>();
const out = computed(() => props.plugin.output);
const name = computed(() => props.plugin.settings.name ?? props.plugin.name);
const foldId = computed(() => `plugin:${props.plugin.id}`);
const shut = computed(() => folded(foldId.value));
const all = computed(() => rowsOf(props.plugin));
const shown = computed(() => all.value.filter((r) => !r.hidden));
const hidden = computed(() => all.value.filter((r) => r.hidden));
const numbered = computed(() => shown.value.filter((r) => typeof r.value === "number"));
const worded = computed(() => shown.value.filter((r) => typeof r.value !== "number"));
const columns = computed(() => {
  const seen: string[] = [];
  for (const row of shown.value) for (const [label] of row.facts) if (!seen.includes(label)) seen.push(label);
  return seen.slice(0, 3);
});
const full = reactive(new Set<string>());
// How long ago it was read, by the Mac's own clock, so a phone that's a
// little fast or slow doesn't matter.
const age = computed(() => (out.value && shire.status ? shire.status.shire.now - out.value.taken + (shire.now - shire.heard) : 0));
const show = (path: string[]) => open({ kind: "item", plugin: props.plugin.id, path });
const width = (value: string | number | null) => `${Math.min(100, Math.max(0, Number(value)))}%`;
</script>

<template>
  <section :id="`card-${plugin.id}`" class="panel">
    <header class="ph">
      <div class="txt">
        <h2>
          <button type="button" class="fold" :aria-expanded="!shut" @click="fold(foldId, !shut)">
            {{ name }}<span class="chev" aria-hidden="true"></span>
          </button>
        </h2>
        <p v-if="out?.summary || plugin.description">{{ out?.summary ?? plugin.description }}</p>
      </div>
      <button type="button" class="icon-btn small" :aria-label="`Options for ${name}`" @click="open({ kind: 'plugin', plugin: plugin.id })">
        <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="4.5" cy="10" r="1.6" fill="currentColor" /><circle cx="10" cy="10" r="1.6" fill="currentColor" /><circle cx="15.5" cy="10" r="1.6" fill="currentColor" /></svg>
      </button>
    </header>

    <template v-if="!shut">
    <p v-if="plugin.problem" class="fix"><b>To fix</b>{{ plugin.problem }}</p>
    <p v-else-if="!out" class="empty">Waiting for its first reading.</p>
    <p v-else-if="!out.ok" class="empty">{{ out.error ? `It couldn't be read. ${out.error}` : out.reason }}</p>

    <template v-if="out">
      <ClaudeCode v-if="plugin.id === 'core-claude-code'" :plugin="plugin" :rows="shown" />

      <template v-else-if="plugin.display === 'gauge'">
        <button v-for="row in numbered" :key="row.key" type="button" class="gg" @click="show(row.path)">
          <span class="gg-top"><span>{{ row.name }}</span><b>{{ valueText(row) }}</b></span>
          <span class="gg-bar" role="img" :aria-label="`${row.name}: ${valueText(row)}`">
            <span :class="{ hot: row.state === 'warn', red: row.state === 'bad' }" :style="{ width: width(row.value) }"></span>
          </span>
          <span v-if="row.mine || row.note" class="gg-cap">{{ row.mine ?? row.note }}</span>
        </button>
        <div v-if="worded.length" class="items">
          <ItemRow v-for="row in worded" :key="row.key" :plugin="plugin" :row="row" />
        </div>
      </template>

      <template v-else-if="plugin.display === 'number'">
        <div v-if="numbered.length" class="nums">
          <button v-for="row in numbered" :key="row.key" type="button" class="num" @click="show(row.path)">
            <span class="num-name">{{ row.name }}</span>
            <span class="val">{{ row.value }}<small v-if="row.unit">{{ row.unit }}</small></span>
            <span v-if="row.mine || row.note" class="ksub">{{ row.mine ?? row.note }}</span>
          </button>
        </div>
        <div v-if="worded.length" class="items">
          <ItemRow v-for="row in worded" :key="row.key" :plugin="plugin" :row="row" />
        </div>
      </template>

      <div v-else-if="plugin.display === 'table'" class="tbl-wrap">
        <table v-if="shown.length" class="tbl">
          <thead><tr><th>Name</th><th>Now</th><th v-for="label in columns" :key="label">{{ label }}</th></tr></thead>
          <tbody>
            <tr v-for="row in shown" :key="row.key" tabindex="0" @click="show(row.path)" @keydown.enter="show(row.path)">
              <td>{{ row.name }}</td>
              <td :class="row.state">{{ valueText(row) || "—" }}</td>
              <td v-for="label in columns" :key="label">{{ row.facts.find(([l]) => l === label)?.[1] ?? "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <template v-else>
        <template v-for="section in sections(shown)" :key="section.title ?? ''">
          <div v-if="section.title" class="label">{{ section.title }}</div>
          <div class="items">
            <ItemRow
              v-for="row in full.has(section.title ?? '') ? section.rows : section.rows.slice(0, LIMIT)"
              :key="row.key" :plugin="plugin" :row="row"
            />
          </div>
          <button
            v-if="section.rows.length > LIMIT && !full.has(section.title ?? '')" type="button" class="morebtn"
            @click="full.add(section.title ?? '')"
          >Show all {{ section.rows.length }}</button>
        </template>
      </template>

      <p v-if="out.ok && !shown.length" class="empty">Nothing to show right now.</p>

      <details v-if="hidden.length" class="item hiddenlist">
        <summary>
          <div class="txt"><div class="nm">Hidden</div><div class="sub">{{ hidden.length }} {{ hidden.length === 1 ? "item" : "items" }} you chose not to see</div></div>
          <span class="chev" aria-hidden="true"></span>
        </summary>
        <div class="more">
          <div v-for="row in hidden" :key="row.key" class="mini">
            <div class="txt"><div class="nm">{{ row.name }}</div></div>
            <button type="button" class="act" @click="choose(plugin.id, row.path, { hidden: null })">Show</button>
          </div>
        </div>
      </details>

      <p class="note-s"><span class="orig">{{ plugin.id }}</span> Read {{ ago(age) }}, and every {{ every(plugin.every) }}.</p>
    </template>
    </template>
  </section>
</template>
