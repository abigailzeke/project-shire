// What the page holds, and the only place that talks to the server.
import { reactive } from "vue";
import { setChoice, type Point } from "./model";
import type { Choice, Groups, Plugin, Settings, Status } from "./types";

/** What's open over the page. */
export type Sheet =
  | { kind: "item"; plugin: string; path: string[] }
  | { kind: "name-item"; plugin: string; path: string[] }
  | { kind: "plugin"; plugin: string }
  | { kind: "name-plugin"; plugin: string }
  | { kind: "move"; plugin: string }
  | { kind: "group"; group: string }
  | { kind: "edit-group"; group: string | null }
  | { kind: "arrange" };

// What you've folded away on this device. It's kept in the browser, so a
// phone and a laptop can each fold what suits them.
const FOLDED = "shire.folded";
function readFolded(): string[] {
  try {
    const found = JSON.parse(localStorage.getItem(FOLDED) ?? "[]");
    return Array.isArray(found) ? found.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export const shire = reactive({
  status: null as Status | null,
  history: {} as Record<string, Point[]>,
  /** When the Mac last answered, and the time now, in seconds. */
  heard: 0,
  now: Date.now() / 1000,
  reading: false,
  /** Why the last read or save didn't work, in plain words. */
  trouble: "",
  sheet: null as Sheet | null,
  folded: readFolded(),
});

export function folded(id: string): boolean {
  return shire.folded.includes(id);
}

export function fold(id: string, shut: boolean): void {
  shire.folded = shire.folded.filter((x) => x !== id).concat(shut ? [id] : []);
  try {
    localStorage.setItem(FOLDED, JSON.stringify(shire.folded));
  } catch { /* a private window: it stays folded until the page is closed */ }
}

async function ask<T>(path: string, body?: unknown): Promise<T> {
  const answer = await fetch(path, body === undefined ? { credentials: "same-origin" } : {
    method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (answer.status === 401) {
    location.reload(); // the key has changed: back to the locked page
    throw new Error("This needs your key.");
  }
  const data = await answer.json().catch(() => null);
  if (!answer.ok) throw new Error(data?.error ?? `The Mac answered ${answer.status}.`);
  return data as T;
}

export async function load(): Promise<void> {
  shire.reading = true;
  try {
    shire.status = await ask<Status>("/api/status");
    shire.heard = Date.now() / 1000;
    if (shire.trouble === NO_WORD) shire.trouble = "";
  } catch {
    shire.trouble = NO_WORD;
  } finally {
    shire.reading = false;
  }
}
const NO_WORD = "Your Mac isn't answering.";

export async function loadHistory(): Promise<void> {
  for (const plugin of shire.status?.plugins ?? []) {
    if (!plugin.enabled || !plugin.history.length) continue;
    try {
      shire.history[plugin.id] = await ask<Point[]>(`/api/history/${encodeURIComponent(plugin.id)}`);
    } catch { /* the next round will try again */ }
  }
}

export function plugin(id: string): Plugin | undefined {
  return shire.status?.plugins.find((p) => p.id === id);
}

/** Saves, then reads the page again, so what's shown is what was kept. */
async function save(run: () => Promise<unknown>): Promise<void> {
  try {
    await run();
    shire.trouble = "";
  } catch (e) {
    shire.trouble = `That wasn't saved. ${(e as Error).message}`;
  }
  await load();
}

function saveSettings(id: string, settings: Settings): Promise<void> {
  const p = plugin(id);
  if (p) p.settings = settings; // shown at once, saved a moment later
  return save(() => ask(`/api/settings/${encodeURIComponent(id)}`, settings));
}

/** Your choice for one item: its name, your line, hidden, or watched. */
export function choose(id: string, path: string[], patch: { [K in keyof Choice]?: Choice[K] | null }): Promise<void> {
  const p = plugin(id);
  return p ? saveSettings(id, setChoice(p.settings, path, patch)) : Promise.resolve();
}

export function switchPlugin(id: string, on: boolean): Promise<void> {
  const p = plugin(id);
  if (!p) return Promise.resolve();
  p.enabled = on;
  return saveSettings(id, { ...p.settings, enabled: on });
}

export function namePlugin(id: string, name: string): Promise<void> {
  const p = plugin(id);
  if (!p) return Promise.resolve();
  const { name: _old, ...rest } = p.settings;
  return saveSettings(id, name.trim() ? { ...rest, name: name.trim() } : rest);
}

export function saveGroups(groups: Groups): Promise<void> {
  if (shire.status) shire.status.groups = groups;
  return save(() => ask("/api/groups", groups));
}

export function open(sheet: Sheet | null): void {
  shire.sheet = sheet;
}
