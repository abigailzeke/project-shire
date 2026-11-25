import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import PluginWidget from "../src/components/PluginWidget.vue";
import GroupBox from "../src/components/GroupBox.vue";
import Snapshot from "../src/components/Snapshot.vue";
import { shire } from "../src/store";
import type { Item, Status } from "../src/types";
import { plugin } from "./helpers";

const items: Item[] = [
  { key: "week", name: "This week", value: 93, unit: "%", state: "warn", note: "Resets Tue 4 pm", facts: { Resets: "Tue 4 pm" } },
  { key: "session", name: "This session", value: 10, unit: "%" },
  { key: "tracker", name: "Usage tracker", value: "asleep", state: "bad" },
];

beforeEach(() => {
  shire.sheet = null;
  shire.status = { shire: { version: "0.2.0", now: 130, system: "macOS" }, groups: [], needs: [], plugins: [] };
  shire.heard = shire.now;
});

describe("the standard widget", () => {
  it("shows a list with your names, and folds away what you hid", () => {
    const settings = { name: "My usage", items: { week: { name: "The week", note: "What I've spent" }, session: { hidden: true } } };
    const w = mount(PluginWidget, { props: { plugin: plugin("usage", items, { settings, output: { plugin: "usage", taken: 100, ok: true, items, summary: "93% of the week" } }) } });
    expect(w.find("h2").text()).toBe("My usage");
    expect(w.find(".ph p").text()).toBe("93% of the week");
    expect(w.findAll(".items > .item .nm").map((n) => n.text())).toEqual(["The week", "Usage tracker"]);
    expect(w.find(".items .sub").text()).toBe("What I've spent");
    expect(w.find(".pill.warn").text()).toBe("93%");
    expect(w.find(".pill.crit").text()).toBe("asleep");
    expect(w.find(".hiddenlist .sub").text()).toBe("1 item you chose not to see");
    expect(w.find(".note-s").text()).toBe("usage Read 30 s ago, and every 1 min.");
  });

  it("shows gauges, filled as far as each number", () => {
    const w = mount(PluginWidget, { props: { plugin: plugin("usage", items, { display: "gauge" }) } });
    expect(w.findAll(".gg").map((g) => g.find("b").text())).toEqual(["93%", "10%"]);
    const bars = w.findAll(".gg-bar > span");
    expect(bars.map((b) => b.attributes("style"))).toEqual(["width: 93%;", "width: 10%;"]);
    expect(bars[0].classes()).toContain("hot");
    expect(w.find(".gg-cap").text()).toBe("Resets Tue 4 pm");
    expect(w.findAll(".items .nm").map((n) => n.text())).toEqual(["Usage tracker"]); // no number, so it's a row
  });

  it("shows numbers", () => {
    const w = mount(PluginWidget, { props: { plugin: plugin("usage", items, { display: "number" }) } });
    expect(w.findAll(".num").map((n) => n.find(".val").text())).toEqual(["93%", "10%"]);
  });

  it("shows a table, with a column for each detail", () => {
    const w = mount(PluginWidget, { props: { plugin: plugin("usage", items, { display: "table" }) } });
    expect(w.findAll("th").map((h) => h.text())).toEqual(["Name", "Now", "Resets"]);
    expect(w.findAll("tbody tr").map((r) => r.findAll("td").map((d) => d.text()))).toEqual(
      [["This week", "93%", "Tue 4 pm"], ["This session", "10%", "—"], ["Usage tracker", "asleep", "—"]]);
  });

  it("opens an item to its details, with watch, rename and hide", async () => {
    const w = mount(PluginWidget, { props: { plugin: plugin("usage", items) } });
    const row = w.find("details.item");
    (row.element as HTMLDetailsElement).open = true;
    await row.trigger("toggle");
    expect(row.find(".facts").text()).toBe("ResetsTue 4 pm");
    expect(row.findAll(".act").map((a) => a.text())).toEqual(["Watch", "Rename", "Hide"]);
    await row.findAll(".act")[1].trigger("click");
    expect(shire.sheet).toEqual({ kind: "name-item", plugin: "usage", path: ["week"] });
  });

  it("says plainly why a plugin has nothing", () => {
    const broken = plugin("p", [], { output: { plugin: "p", taken: 100, ok: false, error: "It took longer than 10 s.", items: [] } });
    expect(mount(PluginWidget, { props: { plugin: broken } }).find(".empty").text()).toBe("It couldn't be read. It took longer than 10 s.");
    const typo = plugin("p", [], { output: null, problem: "plugin.yaml: url is missing" });
    expect(mount(PluginWidget, { props: { plugin: typo } }).find(".fix").text()).toBe("To fixplugin.yaml: url is missing");
  });

  it("gives Claude Code its own widget", () => {
    const code: Item[] = [
      { key: "agent", name: "Claude Code", value: "running", state: "good" },
      { key: "remote-control", name: "Remote Control", value: "off", state: "warn" },
      { key: "session:terminal", name: "Session", value: "2 h", section: "Sessions" },
    ];
    const w = mount(PluginWidget, { props: { plugin: plugin("core-claude-code", code) } });
    expect(w.findAll(".ess-chip").map((c) => [c.find(".nm").text(), c.find(".st").text(), c.classes().includes("warn")])).toEqual(
      [["Claude Code", "running", false], ["Remote Control", "off", true]]);
    expect(w.find(".label").text()).toBe("Sessions");
    expect(w.findAll(".items .nm").map((n) => n.text())).toEqual(["Session"]);
  });
});

describe("the snapshot", () => {
  const mac = plugin("mac", [{ key: "awake", name: "Awake", value: "on", state: "good" }, { key: "network", name: "Network", value: "offline", state: "bad" }],
    { watch: ["awake", "network"], tiles: ["awake"] });
  const base: Status = { shire: { version: "0.2.0", now: 100, system: "macOS" }, groups: [], needs: [], plugins: [mac] };

  it("says all is well when nothing you watch needs you", () => {
    const fine = { ...base, plugins: [plugin("mac", [{ key: "awake", name: "Awake", value: "on", state: "good" }], { watch: ["awake"], tiles: ["awake"] })] };
    const w = mount(Snapshot, { props: { status: fine } });
    expect(w.find(".b-title").text()).toBe("All is well");
    expect(w.find(".banner").classes()).toContain("good");
    expect(w.find(".issues").exists()).toBe(false);
    expect(w.findAll(".kpi h3").map((h) => h.text())).toEqual(["Awake"]);
  });

  it("speaks up for what needs you, and opens it when tapped", async () => {
    const needs = [{ plugin: "mac", key: "network", path: ["network"], name: "Network", why: "bad" as const, value: "offline" }];
    const w = mount(Snapshot, { props: { status: { ...base, needs } } });
    expect(w.find(".b-title").text()).toBe("One thing needs you");
    expect(w.find(".b-sub").text()).toBe("1 of the 2 things you watch are fine");
    expect(w.findAll(".score i").map((i) => i.classes()[0])).toEqual(["good", "crit"]);
    expect(w.find(".issue").text()).toBe("Network: offline");
    await w.find(".issue").trigger("click");
    expect(shire.sheet).toEqual({ kind: "item", plugin: "mac", path: ["network"] });
  });
});

describe("folding", () => {
  beforeEach(() => {
    localStorage.clear();
    shire.folded = [];
  });

  it("folds a widget when its name is tapped, and this device remembers", async () => {
    const w = mount(PluginWidget, { props: { plugin: plugin("usage", items) } });
    expect(w.find(".note-s").exists()).toBe(true);
    await w.find(".fold").trigger("click");
    expect(w.find(".note-s").exists()).toBe(false);
    expect(JSON.parse(localStorage.getItem("shire.folded") ?? "[]")).toEqual(["plugin:usage"]);
    await w.find(".fold").trigger("click");
    expect(w.find(".note-s").exists()).toBe(true);
  });

  it("gives a switched-off plugin no room in its group, and folds the group", async () => {
    const box = {
      group: { id: "mac", name: "Your Mac", plugins: ["usage", "asleep"] }, other: false,
      plugins: [plugin("usage", items), plugin("asleep", [], { enabled: false })],
    };
    const w = mount(GroupBox, { props: { box } });
    expect(w.findAll("section.panel").length).toBe(1);
    expect(w.text()).not.toContain("Switched off");
    await w.find(".sh .fold").trigger("click");
    expect(w.findAll("section.panel").length).toBe(0);
    expect(w.text()).toContain("1 widget, folded away");
  });
});
