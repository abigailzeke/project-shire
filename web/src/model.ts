// What the page works out from the server's answer. Nothing here touches
// the screen or the network, so all of it is tested.
import type { Choice, Choices, Group, Groups, Item, Need, Plugin, Settings, Status } from "./types";

export type Tone = "good" | "warn" | "crit" | "off";

/** An item as the page shows it: what the plugin found, with your choices on top. */
export interface Row {
  key: string;
  /** The keys down to it, when it's a part of another item. */
  path: string[];
  /** What the page calls it: your name for it, or its own. */
  name: string;
  own: string;
  renamed: boolean;
  /** Its own name on the system, when the name shown is a plainer one. */
  original?: string;
  /** A line of your own about it. */
  mine?: string;
  note?: string;
  value: string | number | null;
  unit?: string;
  state?: "good" | "warn" | "bad";
  section?: string;
  facts: [string, string][];
  hidden: boolean;
  watched: boolean;
  /** You watch it, and it isn't there. */
  missing: boolean;
  parts: Row[];
}

function build(items: Item[], choices: Choices, watched: string[], path: string[]): Row[] {
  const rows: Row[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    seen.add(item.key);
    const choice = choices[item.key] ?? {};
    const here = [...path, item.key];
    const shown = choice.name ?? item.name;
    const original = item.original ?? (shown !== item.name ? item.name : undefined);
    rows.push({
      key: item.key,
      path: here,
      name: shown,
      own: item.name,
      renamed: choice.name !== undefined && choice.name !== item.name,
      original: original !== shown ? original : undefined,
      mine: choice.note,
      note: item.note,
      value: item.value ?? null,
      unit: item.unit,
      state: item.state,
      section: item.section,
      facts: Object.entries(item.facts ?? {}).flatMap(([k, v]): [string, string][] =>
        v === null || v === "" ? [] : [[k, v === true ? "yes" : v === false ? "no" : String(v)]]),
      hidden: choice.hidden === true,
      watched: choice.watch ?? watched.includes(item.key),
      missing: false,
      parts: build(item.items ?? [], choice.items ?? {}, [], here),
    });
  }
  // What you watch that isn't there still gets a row, so you can see it's gone.
  for (const key of new Set([...watched, ...Object.keys(choices)])) {
    const choice = choices[key] ?? {};
    if (seen.has(key) || !(choice.watch ?? watched.includes(key))) continue;
    rows.push({
      key, path: [...path, key], name: choice.name ?? key, own: key, renamed: false, mine: choice.note,
      value: null, state: "bad", facts: [], hidden: choice.hidden === true, watched: true, missing: true, parts: [],
    });
  }
  return rows;
}

/** Every item of a plugin, as the page shows it. A plugin that's off has none. */
export function rows(plugin: Plugin): Row[] {
  if (!plugin.enabled || !plugin.output) return [];
  return build(plugin.output.items, plugin.settings.items ?? {}, plugin.watch, []);
}

export function find(all: Row[], path: string[]): Row | undefined {
  const row = all.find((r) => r.key === path[0]);
  return !row || path.length === 1 ? row : find(row.parts, path.slice(1));
}

/** Your choices with one changed. An empty value takes that choice away,
 *  and a choice with nothing left in it is dropped. */
export function setChoice(settings: Settings, path: string[], patch: { [K in keyof Choice]?: Choice[K] | null }): Settings {
  const next = JSON.parse(JSON.stringify(settings)) as Settings;
  const trail: [Choices, string][] = [];
  let level = (next.items ??= {});
  let choice: Choice = {};
  path.forEach((key, i) => {
    trail.push([level, key]);
    choice = level[key] ??= {};
    if (i < path.length - 1) level = choice.items ??= {};
  });
  for (const [field, value] of Object.entries(patch) as [keyof Choice, unknown][]) {
    if (value === undefined || value === null || value === "") delete choice[field];
    else (choice as Record<string, unknown>)[field] = value;
  }
  for (const [at, key] of trail.reverse()) {
    const c = at[key];
    if (c.items && !Object.keys(c.items).length) delete c.items;
    if (!Object.keys(c).length) delete at[key];
  }
  if (!Object.keys(next.items ?? {}).length) delete next.items;
  return next;
}

/** The choice that turns watching on or off, leaving nothing behind when
 *  that's what the plugin does from the start anyway. */
export function watchPatch(plugin: Plugin, row: Row): { watch: boolean | null } {
  const fromTheStart = row.path.length === 1 && plugin.watch.includes(row.key);
  const want = !row.watched;
  return { watch: want === fromTheStart ? null : want };
}

export function valueText(row: Pick<Row, "value" | "unit">): string {
  if (row.value === null || row.value === "") return "";
  if (typeof row.value !== "number") return row.value;
  return `${row.value}${!row.unit ? "" : row.unit === "%" || row.unit === "°" ? row.unit : ` ${row.unit}`}`;
}

export function toneOf(row: Pick<Row, "state">): Tone {
  return row.state === "good" ? "good" : row.state === "warn" ? "warn" : row.state === "bad" ? "crit" : "off";
}

/** What a row's pill says: its value, or a word for its state when it has none. */
export function word(row: Row): string {
  if (row.missing) return "Missing";
  return valueText(row) || (row.state === "good" ? "Fine" : row.state === "warn" ? "Look" : row.state === "bad" ? "Down" : "");
}

/** Rows under their headings, in the order the plugin gave them. */
export function sections(all: Row[]): { title: string | null; rows: Row[] }[] {
  const found: { title: string | null; rows: Row[] }[] = [];
  for (const row of all) {
    const title = row.section ?? null;
    let section = found.find((s) => s.title === title);
    if (!section) found.push((section = { title, rows: [] }));
    section.rows.push(row);
  }
  return found;
}

// ---------------------------------------------------------------- snapshot

export interface Headline {
  tone: "good" | "warn" | "crit";
  title: string;
  sub: string;
}

function flat(all: Row[]): Row[] {
  return all.flatMap((r) => [r, ...flat(r.parts)]);
}

/** Every item you watch, across every plugin that's on. */
export function watching(status: Status): { plugin: Plugin; row: Row }[] {
  return status.plugins.flatMap((plugin) =>
    flat(rows(plugin)).filter((row) => row.watched && !row.hidden).map((row) => ({ plugin, row })));
}

export function headline(needs: Need[], watched: number): Headline {
  const n = needs.length;
  const tone = needs.some((need) => need.why !== "warn") ? "crit" : n ? "warn" : "good";
  const title = !n ? "All is well"
    : tone === "crit" ? (n === 1 ? "One thing needs you" : `${n} things need you`)
    : n === 1 ? "One thing to look at" : `${n} things to look at`;
  const sub = !watched ? "You aren't watching anything yet"
    : !n ? `All ${watched} of the things you watch are fine`
    : `${watched - n} of the ${watched} things you watch are fine`;
  return { tone, title, sub };
}

export function needText(need: Need): string {
  const value = need.value === undefined ? "" : valueText({ value: need.value, unit: need.unit });
  const head = need.why === "missing" ? `${need.name} isn't there` : value ? `${need.name}: ${value}` : need.name;
  const note = need.note?.trim();
  return note ? `${head}. ${note}` : head;
}

export interface TileData {
  plugin: Plugin;
  row: Row;
  colour?: string;
}

/** The tiles the plugins give, in the order of your groups. */
export function tiles(status: Status): TileData[] {
  return arrange(status).flatMap((box) =>
    box.plugins.flatMap((plugin) => {
      const all = rows(plugin);
      return plugin.tiles.flatMap((key) => {
        const row = all.find((r) => r.key === key);
        return row && !row.hidden && !row.missing ? [{ plugin, row, colour: box.group.colour }] : [];
      });
    }));
}

// ------------------------------------------------------------------ groups

export const COLOURS = ["lilac", "blue", "teal", "rose", "sand"] as const;

export interface Box {
  group: Group;
  plugins: Plugin[];
  /** The plugins in no group, gathered at the end. */
  other: boolean;
}

/** Your groups with their plugins, and whatever is in no group at the end. */
export function arrange(status: Status): Box[] {
  const byId = new Map(status.plugins.map((p) => [p.id, p]));
  const placed = new Set<string>();
  const boxes: Box[] = status.groups.map((group) => ({
    group,
    other: false,
    plugins: group.plugins.flatMap((id) => {
      const plugin = byId.get(id);
      if (!plugin || placed.has(id)) return [];
      placed.add(id);
      return [plugin];
    }),
  }));
  const rest = status.plugins.filter((p) => !placed.has(p.id));
  if (rest.length) {
    boxes.push({ group: { id: "", name: "Other", note: "Plugins in no group", plugins: rest.map((p) => p.id) }, plugins: rest, other: true });
  }
  return boxes;
}

const copy = (groups: Groups): Groups => groups.map((g) => ({ ...g, plugins: [...g.plugins] }));

/** Moves a plugin into a group, or out of every group. */
export function movePlugin(groups: Groups, pluginId: string, to: string | null): Groups {
  const next = copy(groups);
  for (const group of next) group.plugins = group.plugins.filter((id) => id !== pluginId);
  next.find((g) => g.id === to)?.plugins.push(pluginId);
  return next;
}

function nudge<T>(list: T[], index: number, by: -1 | 1): T[] {
  const to = index + by;
  if (index < 0 || to < 0 || to >= list.length) return list;
  const next = [...list];
  [next[index], next[to]] = [next[to], next[index]];
  return next;
}

/** Moves a plugin one place up or down inside its group. */
export function nudgePlugin(groups: Groups, pluginId: string, by: -1 | 1): Groups {
  return copy(groups).map((g) => ({ ...g, plugins: nudge(g.plugins, g.plugins.indexOf(pluginId), by) }));
}

/** Moves a group one place up or down the page. */
export function nudgeGroup(groups: Groups, groupId: string, by: -1 | 1): Groups {
  return nudge(copy(groups), groups.findIndex((g) => g.id === groupId), by);
}

/** An id for a new group, made from its name, that no other group has. */
export function newGroupId(groups: Groups, name: string): string {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 30) || "group";
  let id = base;
  for (let n = 2; groups.some((g) => g.id === id); n++) id = `${base}-${n}`;
  return id;
}

// ----------------------------------------------------------------- history

export interface Point {
  t: number;
  [key: string]: number;
}

export function series(points: Point[], key: string): { t: number; v: number }[] {
  return points.filter((p) => typeof p[key] === "number").map((p) => ({ t: p.t, v: p[key] }));
}

export interface Slot {
  kind: "good" | "warn" | "crit" | "none";
  from: number;
}

/** 24 hours as 48 half-hour slots: green when it was good the whole time. */
export function availability(points: Point[], key: string, now: number): { slots: Slot[]; percent: number | null } {
  const SLOTS = 48, SLOT = 1800, start = now - SLOTS * SLOT;
  const tally = Array.from({ length: SLOTS }, () => ({ up: 0, n: 0 }));
  for (const { t, v } of series(points, key)) {
    if (t < start) continue;
    const slot = tally[Math.min(SLOTS - 1, Math.floor((t - start) / SLOT))];
    slot.n++;
    if (v > 0) slot.up++;
  }
  const n = tally.reduce((a, s) => a + s.n, 0), up = tally.reduce((a, s) => a + s.up, 0);
  return {
    slots: tally.map((s, i) => ({ kind: !s.n ? "none" : s.up === s.n ? "good" : s.up === 0 ? "crit" : "warn", from: start + i * SLOT })),
    percent: n ? (100 * up) / n : null,
  };
}

// ------------------------------------------------------------------- words

export function ago(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 10) return "just now";
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function every(seconds: number): string {
  return seconds % 3600 === 0 ? `${seconds / 3600} h` : seconds % 60 === 0 ? `${seconds / 60} min` : `${seconds} s`;
}

export function clock(t: number): string {
  return new Date(t * 1000).toLocaleTimeString("en-GB", { hour: "numeric", minute: "2-digit", hour12: true }).toLowerCase();
}
