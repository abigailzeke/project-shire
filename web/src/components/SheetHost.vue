<script setup lang="ts">
// What opens over the page: an item's details, a menu, or a short form.
// From the bottom on a phone, centred on a laptop.
import { computed, ref, watch } from "vue";
import { COLOURS, find, movePlugin, newGroupId, nudgeGroup, nudgePlugin, rows, valueText } from "../model";
import { choose, namePlugin, open, plugin as pluginOf, saveGroups, shire, switchPlugin } from "../store";
import ItemDetails from "./ItemDetails.vue";

const sheet = computed(() => shire.sheet);
const groups = computed(() => shire.status?.groups ?? []);
const thePlugin = computed(() => (sheet.value && "plugin" in sheet.value ? pluginOf(sheet.value.plugin) : undefined));
const pluginName = computed(() => thePlugin.value?.settings.name ?? thePlugin.value?.name ?? "");
const theRow = computed(() => {
  const s = sheet.value;
  return thePlugin.value && s && (s.kind === "item" || s.kind === "name-item") ? find(rows(thePlugin.value), s.path) : undefined;
});
const theGroup = computed(() => {
  const s = sheet.value;
  return s && (s.kind === "group" || s.kind === "edit-group") ? groups.value.find((g) => g.id === s.group) : undefined;
});
const home = computed(() => groups.value.find((g) => thePlugin.value && g.plugins.includes(thePlugin.value.id)));

const title = computed(() => {
  const s = sheet.value;
  if (!s) return "";
  if (s.kind === "item") return theRow.value?.name ?? "Gone";
  if (s.kind === "name-item") return `Rename ${theRow.value?.own ?? "it"}`;
  if (s.kind === "plugin") return pluginName.value;
  if (s.kind === "name-plugin") return `Rename ${thePlugin.value?.name ?? "it"}`;
  if (s.kind === "move") return `Move ${pluginName.value} to`;
  if (s.kind === "group") return theGroup.value?.name ?? "Group";
  if (s.kind === "edit-group") return s.group ? "Edit this group" : "A new group";
  return "Plugins and groups";
});
const sub = computed(() => {
  const s = sheet.value;
  if (s?.kind === "item" && theRow.value) return [pluginName.value, valueText(theRow.value)].filter(Boolean).join(" · ");
  if (s?.kind === "arrange") return "Switch a plugin on or off. Saved for every device.";
  return "";
});

// The short forms: a name, a line of your own, and a colour.
const name = ref("");
const note = ref("");
const colour = ref("");
watch(sheet, (s) => {
  if (s?.kind === "name-item") [name.value, note.value] = [theRow.value?.name ?? "", theRow.value?.mine ?? ""];
  if (s?.kind === "name-plugin") name.value = pluginName.value;
  if (s?.kind === "edit-group") [name.value, note.value, colour.value] = [theGroup.value?.name ?? "", theGroup.value?.note ?? "", theGroup.value?.colour ?? ""];
});

function saveItemName(clear = false) {
  const s = sheet.value, row = theRow.value;
  if (s?.kind !== "name-item" || !row) return;
  const mine = name.value.trim();
  choose(s.plugin, s.path, clear ? { name: null, note: null } : { name: mine && mine !== row.own ? mine : null, note: note.value.trim() || null });
  open(null);
}

function savePluginName(clear = false) {
  const s = sheet.value, p = thePlugin.value;
  if (s?.kind !== "name-plugin" || !p) return;
  const mine = name.value.trim();
  namePlugin(p.id, clear || mine === p.name ? "" : mine);
  open(null);
}

function saveGroup() {
  const s = sheet.value;
  if (s?.kind !== "edit-group" || !name.value.trim()) return;
  const fields = {
    name: name.value.trim(),
    ...(note.value.trim() ? { note: note.value.trim() } : {}),
    ...(colour.value ? { colour: colour.value } : {}),
  };
  const old = theGroup.value;
  saveGroups(old
    ? groups.value.map((g) => (g.id === old.id ? { id: g.id, ...fields, plugins: g.plugins } : g))
    : [...groups.value, { id: newGroupId(groups.value, fields.name), ...fields, plugins: [] }]);
  open(null);
}

function then(run: () => unknown) {
  run();
  open(null);
}
</script>

<template>
  <div v-if="sheet" class="sheet" @click.self="open(null)">
    <section class="panel sheet-card" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
      <header class="ph">
        <div class="txt"><h2 id="sheet-title">{{ title }}</h2><p v-if="sub">{{ sub }}</p></div>
        <button type="button" class="icon-btn" aria-label="Close" @click="open(null)">
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" /></svg>
        </button>
      </header>

      <template v-if="sheet.kind === 'item'">
        <ItemDetails v-if="thePlugin && theRow" :plugin="thePlugin" :row="theRow" />
        <p v-else class="empty">It isn't there any more.</p>
      </template>

      <form v-else-if="sheet.kind === 'name-item'" class="form" @submit.prevent="saveItemName()">
        <label class="field">Your name for it<input v-model="name" maxlength="200" :placeholder="theRow?.own" autocomplete="off" /></label>
        <label class="field">A line of your own about it<input v-model="note" maxlength="300" placeholder="What it is to you" autocomplete="off" /></label>
        <div class="form-btns">
          <button type="submit" class="btn primary">Save</button>
          <button type="button" class="btn" @click="saveItemName(true)">Use its own name</button>
        </div>
      </form>

      <form v-else-if="sheet.kind === 'name-plugin'" class="form" @submit.prevent="savePluginName()">
        <label class="field">Your name for it<input v-model="name" maxlength="60" :placeholder="thePlugin?.name" autocomplete="off" /></label>
        <div class="form-btns">
          <button type="submit" class="btn primary">Save</button>
          <button type="button" class="btn" @click="savePluginName(true)">Use its own name</button>
        </div>
      </form>

      <div v-else-if="sheet.kind === 'plugin' && thePlugin" class="menu">
        <button type="button" @click="open({ kind: 'name-plugin', plugin: thePlugin.id })">Rename</button>
        <button type="button" @click="open({ kind: 'move', plugin: thePlugin.id })">Move to another group</button>
        <button type="button" :disabled="!home || home.plugins[0] === thePlugin.id" @click="then(() => saveGroups(nudgePlugin(groups, thePlugin!.id, -1)))">Move up</button>
        <button type="button" :disabled="!home || home.plugins[home.plugins.length - 1] === thePlugin.id" @click="then(() => saveGroups(nudgePlugin(groups, thePlugin!.id, 1)))">Move down</button>
        <button type="button" class="danger" @click="then(() => switchPlugin(thePlugin!.id, false))">Turn off</button>
      </div>

      <div v-else-if="sheet.kind === 'move' && thePlugin" class="menu">
        <button
          v-for="group in groups" :key="group.id" type="button" :disabled="group.id === home?.id"
          @click="then(() => saveGroups(movePlugin(groups, thePlugin!.id, group.id)))"
        >{{ group.name }}<small v-if="group.id === home?.id">it's here</small></button>
        <button type="button" :disabled="!home" @click="then(() => saveGroups(movePlugin(groups, thePlugin!.id, null)))">No group</button>
      </div>

      <div v-else-if="sheet.kind === 'group' && theGroup" class="menu">
        <button type="button" @click="open({ kind: 'edit-group', group: theGroup.id })">Name and colour</button>
        <button type="button" :disabled="groups[0]?.id === theGroup.id" @click="then(() => saveGroups(nudgeGroup(groups, theGroup!.id, -1)))">Move up</button>
        <button type="button" :disabled="groups[groups.length - 1]?.id === theGroup.id" @click="then(() => saveGroups(nudgeGroup(groups, theGroup!.id, 1)))">Move down</button>
        <button type="button" class="danger" @click="then(() => saveGroups(groups.filter((g) => g.id !== theGroup!.id)))">Remove this group<small>its plugins stay</small></button>
      </div>

      <form v-else-if="sheet.kind === 'edit-group'" class="form" @submit.prevent="saveGroup">
        <label class="field">Its name<input v-model="name" maxlength="60" required autocomplete="off" /></label>
        <label class="field">A line of your own under the name<input v-model="note" maxlength="300" autocomplete="off" /></label>
        <div class="field">Its colour
          <div class="swatches">
            <button type="button" class="swatch none" :aria-pressed="colour === ''" aria-label="No colour" @click="colour = ''"></button>
            <button
              v-for="c in COLOURS" :key="c" type="button" class="swatch" :class="`tone-${c}`"
              :aria-pressed="colour === c" :aria-label="c" @click="colour = c"
            ></button>
          </div>
        </div>
        <div class="form-btns"><button type="submit" class="btn primary">Save</button></div>
      </form>

      <template v-else-if="sheet.kind === 'arrange'">
        <div v-for="p in shire.status?.plugins ?? []" :key="p.id" class="mini">
          <div class="txt"><div class="nm">{{ p.settings.name ?? p.name }}</div><div class="sub">{{ p.description ?? p.id }}</div></div>
          <button
            type="button" class="switch" role="switch" :aria-checked="p.enabled" :aria-label="`${p.settings.name ?? p.name}: ${p.enabled ? 'on' : 'off'}`"
            @click="switchPlugin(p.id, !p.enabled)"
          ><i></i></button>
        </div>
        <div class="form-btns"><button type="button" class="btn" @click="open({ kind: 'edit-group', group: null })">Add a group</button></div>
      </template>
    </section>
  </div>
</template>
