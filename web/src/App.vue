<script setup lang="ts">
// The page: the snapshot at the top, then your groups, each holding its
// widgets. It asks the Mac again every ten seconds while it's on screen.
import { computed, nextTick, onMounted, onUnmounted } from "vue";
import GroupBox from "./components/GroupBox.vue";
import SheetHost from "./components/SheetHost.vue";
import Snapshot from "./components/Snapshot.vue";
import { ago, arrange } from "./model";
import { load, loadHistory, open, shire } from "./store";

const boxes = computed(() => (shire.status ? arrange(shire.status) : []));
const quiet = computed(() => shire.heard > 0 && shire.now - shire.heard > 45);
const title = computed(() => (!shire.status || shire.status.shire.system === "macOS" ? "Your Mac" : "Your computer"));
const live = computed(() =>
  !shire.heard ? (shire.trouble || "Reading your Mac…")
    : quiet.value ? `No word from your Mac since ${ago(shire.now - shire.heard)}`
    : `Updated ${ago(shire.now - shire.heard)}`);

let timers: number[] = [];
const whenSeen = () => { if (!document.hidden) void load(); };
const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") open(null); };

onMounted(async () => {
  document.addEventListener("visibilitychange", whenSeen);
  document.addEventListener("keydown", onKey);
  timers = [
    window.setInterval(() => { shire.now = Date.now() / 1000; }, 5_000),
    window.setInterval(whenSeen, 10_000),
    window.setInterval(() => { if (!document.hidden) void loadHistory(); }, 60_000),
  ];
  await load();
  // A link that ends in a widget's name, like /#card-core-docker, opens at that widget.
  await nextTick();
  if (location.hash.length > 1) document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView();
  await loadHistory();
});
onUnmounted(() => {
  timers.forEach((t) => window.clearInterval(t));
  document.removeEventListener("visibilitychange", whenSeen);
  document.removeEventListener("keydown", onKey);
});
</script>

<template>
  <header class="top">
    <div class="txt">
      <p class="kicker">Project Shire</p>
      <h1>{{ title }}</h1>
      <p class="live" :class="{ stale: quiet || (!shire.heard && shire.trouble) }">
        <span class="pulse" aria-hidden="true"></span><span>{{ live }}</span>
      </p>
    </div>
    <div class="top-btns">
      <button type="button" class="icon-btn" aria-label="Plugins and groups" @click="open({ kind: 'arrange' })">
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 6h13M3.5 14h13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" /><circle cx="7.5" cy="6" r="2.2" fill="var(--surface)" stroke="currentColor" stroke-width="1.8" /><circle cx="12.5" cy="14" r="2.2" fill="var(--surface)" stroke="currentColor" stroke-width="1.8" /></svg>
      </button>
      <button type="button" class="icon-btn" :class="{ spin: shire.reading }" aria-label="Refresh now" @click="load()">
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M16.2 10a6.2 6.2 0 1 1-1.8-4.4M16.2 3.6v3.6h-3.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" /></svg>
      </button>
    </div>
  </header>

  <p v-if="shire.trouble && shire.heard" class="fix" role="alert"><b>Trouble</b>{{ shire.trouble }}</p>

  <template v-if="shire.status">
    <Snapshot :status="shire.status" />
    <GroupBox v-for="box in boxes" :key="box.group.id || 'no-group'" :box="box" />
    <footer class="foot">Project Shire {{ shire.status.shire.version }}</footer>
  </template>

  <SheetHost />
</template>
