import type { Item, Plugin } from "../src/types";

/** A plugin as the server hands it to the page, with only what a test cares about filled in. */
export function plugin(id: string, items: Item[], more: Partial<Plugin> = {}): Plugin {
  return {
    id, name: id, core: false, enabled: true, display: "list", every: 60, history: [], watch: [], tiles: [], settings: {},
    output: { plugin: id, taken: 100, ok: true, items }, ...more,
  };
}
