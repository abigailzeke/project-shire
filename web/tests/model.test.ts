import { describe, expect, it } from "vitest";
import {
  arrange, availability, find, headline, movePlugin, needText, newGroupId, nudgeGroup, nudgePlugin, rows, sections,
  setChoice, tiles, valueText, watchPatch, watching,
} from "../src/model";
import type { Item, Plugin, Settings, Status } from "../src/types";
import { plugin } from "./helpers";

const status = (plugins: Plugin[], more: Partial<Status> = {}): Status =>
  ({ shire: { version: "0.2.0", now: 100, system: "macOS" }, groups: [], needs: [], plugins, ...more });

const wallet: Item = { key: "wallet", name: "wallet", value: "up", state: "good", facts: { containers: 7, healthy: true, gone: null },
  items: [{ key: "web", name: "web", value: "Up 2 hours", state: "good" }, { key: "db", name: "postgres", state: "bad" }] };

describe("rows", () => {
  it("shows what the plugin found, with your choices on top", () => {
    const settings: Settings = { items: { wallet: { name: "Wallet", note: "My money app", watch: true,
      items: { web: { name: "Screens" }, db: { hidden: true } } } } };
    const [row] = rows(plugin("docker", [wallet], { settings }));
    expect(row).toMatchObject({ name: "Wallet", own: "wallet", renamed: true, mine: "My money app", watched: true, hidden: false, missing: false });
    expect(row.facts).toEqual([["containers", "7"], ["healthy", "yes"]]);
    expect(row.parts.map((p) => [p.name, p.hidden, p.path])).toEqual([["Screens", false, ["wallet", "web"]], ["postgres", true, ["wallet", "db"]]]);
  });

  it("watches what the plugin says to watch, until you say otherwise", () => {
    const awake: Item = { key: "awake", name: "Awake", value: "on", state: "good" };
    expect(rows(plugin("mac", [awake], { watch: ["awake"] }))[0].watched).toBe(true);
    expect(rows(plugin("mac", [awake], { watch: ["awake"], settings: { items: { awake: { watch: false } } } }))[0].watched).toBe(false);
  });

  it("keeps a row for something you watch that isn't there", () => {
    const settings: Settings = { items: { Obsidian: { watch: true, note: "My vault" }, Notes: { note: "not watched" } } };
    const all = rows(plugin("apps", [], { settings, watch: ["Finder"] }));
    expect(all.map((r) => [r.name, r.missing, r.state])).toEqual([["Finder", true, "bad"], ["Obsidian", true, "bad"]]);
  });

  it("has nothing for a plugin that's off or hasn't run", () => {
    expect(rows(plugin("p", [wallet], { enabled: false }))).toEqual([]);
    expect(rows(plugin("p", [], { output: null }))).toEqual([]);
  });

  it("finds a part by its path", () => {
    expect(find(rows(plugin("docker", [wallet])), ["wallet", "db"])?.name).toBe("postgres");
    expect(find(rows(plugin("docker", [wallet])), ["wallet", "nothing"])).toBeUndefined();
  });

  it("gathers rows under their headings, in order", () => {
    const items: Item[] = [{ key: "a", name: "A", section: "Apps" }, { key: "b", name: "B" }, { key: "c", name: "C", section: "Apps" }];
    expect(sections(rows(plugin("p", items))).map((s) => [s.title, s.rows.map((r) => r.key)])).toEqual([["Apps", ["a", "c"]], [null, ["b"]]]);
  });
});

describe("setChoice", () => {
  it("sets a choice, and a part's choice inside its item's", () => {
    expect(setChoice({}, ["wallet"], { name: "Wallet" })).toEqual({ items: { wallet: { name: "Wallet" } } });
    expect(setChoice({ enabled: true }, ["wallet", "web"], { hidden: true }))
      .toEqual({ enabled: true, items: { wallet: { items: { web: { hidden: true } } } } });
  });

  it("takes a choice away, and drops what's left empty", () => {
    const settings: Settings = { name: "Mine", items: { wallet: { name: "Wallet", items: { web: { hidden: true } } } } };
    expect(setChoice(settings, ["wallet", "web"], { hidden: null })).toEqual({ name: "Mine", items: { wallet: { name: "Wallet" } } });
    expect(setChoice(setChoice(settings, ["wallet", "web"], { hidden: null }), ["wallet"], { name: "" })).toEqual({ name: "Mine" });
  });

  it("keeps an original name to show under a plainer one", () => {
    const job: Item = { key: "com.x.agent", name: "X updater", original: "com.x.agent" };
    expect(rows(plugin("jobs", [job]))[0].original).toBe("com.x.agent");
    const mine = rows(plugin("jobs", [job, wallet], { settings: { items: { "com.x.agent": { name: "My updater" }, wallet: { name: "Wallet" } } } }));
    expect(mine.map((r) => [r.name, r.own, r.original])).toEqual([["My updater", "X updater", "com.x.agent"], ["Wallet", "wallet", "wallet"]]);
    expect(rows(plugin("docker", [wallet]))[0].original).toBeUndefined();
  });

  it("leaves the settings it was given alone", () => {
    const settings: Settings = { items: { a: { name: "A" } } };
    setChoice(settings, ["a"], { name: "B" });
    expect(settings).toEqual({ items: { a: { name: "A" } } });
  });

  it("turns watching on and off without leaving anything behind", () => {
    const awake: Item = { key: "awake", name: "Awake" };
    const p = plugin("mac", [awake, { key: "power", name: "Battery" }], { watch: ["awake"] });
    const [a, power] = rows(p);
    expect(watchPatch(p, a)).toEqual({ watch: false });
    expect(watchPatch(p, power)).toEqual({ watch: true });
    const stopped = plugin("mac", [awake], { watch: ["awake"], settings: { items: { awake: { watch: false } } } });
    expect(watchPatch(stopped, rows(stopped)[0])).toEqual({ watch: null });
  });
});

describe("the snapshot", () => {
  it("says all is well, or how many things need you", () => {
    expect(headline([], 5)).toEqual({ tone: "good", title: "All is well", sub: "All 5 of the things you watch are fine" });
    const amber = { plugin: "p", key: "a", path: ["a"], name: "A", why: "warn" as const };
    expect(headline([amber], 5)).toMatchObject({ tone: "warn", title: "One thing to look at", sub: "4 of the 5 things you watch are fine" });
    expect(headline([amber, { ...amber, why: "missing" }], 5)).toMatchObject({ tone: "crit", title: "2 things need you" });
    expect(headline([], 0).sub).toBe("You aren't watching anything yet");
  });

  it("puts what needs you in plain words", () => {
    expect(needText({ plugin: "p", key: "a", path: ["a"], name: "This week", why: "warn", value: 93, unit: "%", note: "Resets Tue" }))
      .toBe("This week: 93%. Resets Tue");
    expect(needText({ plugin: "p", key: "a", path: ["a"], name: "Obsidian", why: "missing" })).toBe("Obsidian isn't there");
  });

  it("counts every item you watch, parts too, and none that's hidden", () => {
    const settings: Settings = { items: { wallet: { watch: true, items: { web: { watch: true }, db: { watch: true, hidden: true } } } } };
    expect(watching(status([plugin("docker", [wallet], { settings })])).map((w) => w.row.key)).toEqual(["wallet", "web"]);
  });

  it("takes its tiles from the plugins, in the order of your groups", () => {
    const mac = plugin("mac", [{ key: "awake", name: "Awake", value: "on" }, { key: "power", name: "Battery", value: 80, unit: "%" }], { tiles: ["power", "nothing"] });
    const agent = plugin("agent", [{ key: "agent", name: "Claude Code", value: "running" }], { tiles: ["agent"] });
    const s = status([mac, agent], { groups: [{ id: "a", name: "Robin", colour: "lilac", plugins: ["agent"] }] });
    expect(tiles(s).map((t) => [t.row.name, t.colour])).toEqual([["Claude Code", "lilac"], ["Battery", undefined]]);
  });

  it("writes a value with its unit", () => {
    expect([valueText({ value: 43, unit: "%" }), valueText({ value: 12, unit: "ms" }), valueText({ value: "running" }), valueText({ value: null })])
      .toEqual(["43%", "12 ms", "running", ""]);
  });
});

describe("groups", () => {
  const groups = [{ id: "mac", name: "Your Mac", plugins: ["a", "b"] }, { id: "agent", name: "Your agent", plugins: ["c"] }];

  it("puts what's in no group at the end, and skips what isn't there", () => {
    const boxes = arrange(status([plugin("a", []), plugin("c", []), plugin("mine", [])], { groups }));
    expect(boxes.map((b) => [b.group.name, b.plugins.map((p) => p.id), b.other])).toEqual(
      [["Your Mac", ["a"], false], ["Your agent", ["c"], false], ["Other", ["mine"], true]]);
  });

  it("moves a plugin between groups, and out of every group", () => {
    expect(movePlugin(groups, "a", "agent").map((g) => g.plugins)).toEqual([["b"], ["c", "a"]]);
    expect(movePlugin(groups, "a", null).map((g) => g.plugins)).toEqual([["b"], ["c"]]);
    expect(groups[0].plugins).toEqual(["a", "b"]);
  });

  it("moves a plugin or a group one place, and stops at the ends", () => {
    expect(nudgePlugin(groups, "a", 1)[0].plugins).toEqual(["b", "a"]);
    expect(nudgePlugin(groups, "a", -1)[0].plugins).toEqual(["a", "b"]);
    expect(nudgeGroup(groups, "agent", -1).map((g) => g.id)).toEqual(["agent", "mac"]);
    expect(nudgeGroup(groups, "agent", 1).map((g) => g.id)).toEqual(["mac", "agent"]);
  });

  it("makes an id for a new group that no other has", () => {
    expect(newGroupId(groups, "Home Lab")).toBe("home-lab");
    expect(newGroupId(groups, "Mac")).toBe("mac-2");
    expect(newGroupId(groups, "···")).toBe("group");
  });
});

describe("history", () => {
  it("turns 24 hours into half-hour bars", () => {
    const now = 48 * 1800;
    const { slots, percent } = availability([{ t: now - 100, up: 1 }, { t: now - 200, up: 0 }, { t: now - 4000, up: 1 }, { t: 10, up: 0 }], "up", now);
    expect(slots.length).toBe(48);
    expect([slots[47].kind, slots[45].kind, slots[0].kind, slots[20].kind]).toEqual(["warn", "good", "crit", "none"]);
    expect(percent).toBe(50);
    expect(availability([], "up", now).percent).toBeNull();
  });
});
