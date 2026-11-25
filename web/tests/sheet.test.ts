import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SheetHost from "../src/components/SheetHost.vue";
import { open, shire } from "../src/store";
import type { Status } from "../src/types";
import { plugin } from "./helpers";

// Every save the page makes, as [address, what was sent].
let saved: [string, unknown][] = [];

beforeEach(() => {
  saved = [];
  const status: Status = {
    shire: { version: "0.2.0", now: 100, system: "macOS" },
    needs: [],
    groups: [{ id: "mac", name: "Your Mac", plugins: ["usage", "docker"] }, { id: "agent", name: "Your agent", colour: "lilac", plugins: [] }],
    plugins: [plugin("usage", [{ key: "week", name: "This week", value: 8, unit: "%", facts: { Resets: "Tue" } }]), plugin("docker", [])],
  };
  shire.status = status;
  shire.sheet = null;
  shire.trouble = "";
  vi.stubGlobal("fetch", vi.fn(async (address: string, init?: RequestInit) => {
    const sent = init?.body ? JSON.parse(String(init.body)) : undefined;
    if (init?.method === "PUT") saved.push([address, sent]);
    return { ok: true, status: 200, json: async () => sent ?? shire.status };
  }));
});

async function show(sheet: Parameters<typeof open>[0]) {
  const w = mount(SheetHost);
  open(sheet);
  await flushPromises();
  return w;
}

describe("the sheet", () => {
  it("opens an item to its details", async () => {
    const w = await show({ kind: "item", plugin: "usage", path: ["week"] });
    expect(w.find("#sheet-title").text()).toBe("This week");
    expect(w.find(".ph p").text()).toBe("usage · 8%");
    expect(w.find(".facts").text()).toBe("ResetsTue");
  });

  it("renames an item, with a line of your own", async () => {
    const w = await show({ kind: "name-item", plugin: "usage", path: ["week"] });
    const [name, note] = w.findAll("input");
    expect((name.element as HTMLInputElement).value).toBe("This week");
    await name.setValue("The week");
    await note.setValue("What I've spent");
    await w.find("form").trigger("submit");
    await flushPromises();
    expect(saved).toEqual([["/api/settings/usage", { items: { week: { name: "The week", note: "What I've spent" } } }]]);
    expect(shire.sheet).toBeNull();
  });

  it("keeps no name when you leave it as its own", async () => {
    const w = await show({ kind: "name-item", plugin: "usage", path: ["week"] });
    await w.find("form").trigger("submit");
    await flushPromises();
    expect(saved).toEqual([["/api/settings/usage", {}]]);
  });

  it("renames a plugin and turns one off", async () => {
    let w = await show({ kind: "name-plugin", plugin: "usage" });
    await w.find("input").setValue("My usage");
    await w.find("form").trigger("submit");
    await flushPromises();
    w = await show({ kind: "plugin", plugin: "usage" });
    await w.findAll(".menu button").find((b) => b.text() === "Turn off")!.trigger("click");
    await flushPromises();
    expect(saved).toEqual([["/api/settings/usage", { name: "My usage" }], ["/api/settings/usage", { name: "My usage", enabled: false }]]);
  });

  it("moves a plugin down, and to another group", async () => {
    let w = await show({ kind: "plugin", plugin: "usage" });
    const [, , up, down] = w.findAll(".menu button");
    expect([up.attributes("disabled"), down.attributes("disabled")]).toEqual(["", undefined]); // it's first, so it can't go up
    await down.trigger("click");
    await flushPromises();
    w = await show({ kind: "move", plugin: "usage" });
    await w.findAll(".menu button").find((b) => b.text() === "Your agent")!.trigger("click");
    await flushPromises();
    expect(saved.map(([address, groups]) => [address, (groups as { plugins: string[] }[]).map((g) => g.plugins)])).toEqual(
      [["/api/groups", [["docker", "usage"], []]], ["/api/groups", [["docker"], ["usage"]]]]);
  });

  it("makes a new group, and recolours and removes one", async () => {
    let w = await show({ kind: "edit-group", group: null });
    await w.findAll("input")[0].setValue("Home Lab");
    await w.find(".swatch.tone-teal").trigger("click");
    await w.find("form").trigger("submit");
    await flushPromises();
    expect((saved[0][1] as object[])[2]).toEqual({ id: "home-lab", name: "Home Lab", colour: "teal", plugins: [] });

    w = await show({ kind: "edit-group", group: "agent" });
    await w.find(".swatch.none").trigger("click");
    await w.find("form").trigger("submit");
    await flushPromises();
    expect((saved[1][1] as object[])[1]).toEqual({ id: "agent", name: "Your agent", plugins: [] });

    w = await show({ kind: "group", group: "mac" });
    await w.find(".menu button.danger").trigger("click");
    await flushPromises();
    expect((saved[2][1] as { id: string }[]).map((g) => g.id)).toEqual(["agent", "home-lab"]);
  });

  it("switches plugins on and off from one list", async () => {
    const w = await show({ kind: "arrange" });
    expect(w.findAll(".switch").map((s) => s.attributes("aria-checked"))).toEqual(["true", "true"]);
    await w.findAll(".switch")[1].trigger("click");
    await flushPromises();
    expect(saved).toEqual([["/api/settings/docker", { enabled: false }]]);
  });

  it("switches on a plugin that comes switched off", async () => {
    shire.status!.plugins.push(plugin("vault", [], { enabled: false }));
    const w = await show({ kind: "arrange" });
    expect(w.findAll(".switch").map((s) => s.attributes("aria-checked"))).toEqual(["true", "true", "false"]);
    await w.findAll(".switch")[2].trigger("click");
    await flushPromises();
    expect(saved).toEqual([["/api/settings/vault", { enabled: true }]]);
  });

  it("says so when a save doesn't work", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_: string, init?: RequestInit) =>
      init?.method === "PUT" ? { ok: false, status: 400, json: async () => ({ error: "name should be text" }) }
        : { ok: true, status: 200, json: async () => shire.status }));
    const w = await show({ kind: "name-plugin", plugin: "usage" });
    await w.find("input").setValue("Mine");
    await w.find("form").trigger("submit");
    await flushPromises();
    expect(shire.trouble).toBe("That wasn't saved. name should be text");
  });
});
