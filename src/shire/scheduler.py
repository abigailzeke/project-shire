"""The scheduler: calls each plugin when its time comes, and saves what it
found.

Every few seconds it looks for plugins again, so a folder you drop into your
space is picked up without a restart, and a plugin.yaml you change runs at
once. Each plugin has its own schedule, `every:` in its plugin.yaml, and its
own time limit. They run side by side, so a slow one never holds up the rest.

The scheduler writes only into data/. Your choices, in user-settings/, are only
ever read here, and nothing is ever written into your plugins folder."""

from __future__ import annotations

import fnmatch
import sys
import threading
import time
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor

from . import checks, plugins, schemas, store

HISTORY_HOURS = 24
HISTORY_STEP = 60  # at most one history point a minute


def finish(plugin, result: dict, taken: int, took_ms: int) -> dict:
    """A check's result as the output that's saved: the scheduler's own
    fields added, and the whole thing held to the standard format."""
    ours = {"plugin": plugin.id, "taken": taken, "took_ms": took_ms}
    output = {"ok": True, "items": [], **result, **ours}
    found = schemas.problems("output", output)
    if not found:
        twice = [key for key, n in Counter(item["key"] for item in output["items"]).items() if n > 1]
        if twice:
            found = [f"two items share the key {twice[0]!r}"]
    if found:
        return {**ours, "ok": False, "error": f"Its output isn't in the standard format: {found[0]}.", "items": []}
    return output


def keep_history(plugin, output: dict, folder) -> None:
    """Adds the items named in `history:` to the plugin's last 24 hours: an
    item's number, or 1 or 0 for whether it was good when it has no number."""
    wanted = plugin.config.get("history") or []
    if not wanted or not output["ok"]:
        return
    point = {"t": output["taken"]}
    for item in output["items"]:
        value = item.get("value")
        if item["key"] not in wanted:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            point[item["key"]] = value
        elif "state" in item:
            point[item["key"]] = int(item["state"] == "good")
    path = folder / "history.json"
    points = store.read_json(path, [])
    if not isinstance(points, list):
        points = []
    if points and output["taken"] - points[-1].get("t", 0) < HISTORY_STEP - 5:
        return
    cutoff = output["taken"] - HISTORY_HOURS * 3600
    store.write_json(path, [p for p in points if p.get("t", 0) >= cutoff] + [point])


def plain_names(names: dict, items: list) -> None:
    """Gives each item the plain name its plugin's names.yaml has for it, and
    keeps the name it had as `original`, so the page can show both. A line
    matches an item's key or its name, and the first that matches wins."""
    for item in items:
        if not isinstance(item, dict):
            continue
        key, name = item.get("key"), item.get("name")
        for pattern, plain in names.items():
            if any(isinstance(text, str) and fnmatch.fnmatchcase(text, pattern) for text in (key, name)):
                if plain != name:
                    item.setdefault("original", name)
                    item["name"] = plain
                break
        if isinstance(item.get("items"), list):
            plain_names(names, item["items"])


def run(plugin) -> dict:
    """Runs one plugin now and saves what it found."""
    taken, started = int(time.time()), time.monotonic()
    result = checks.run(plugin)
    if plugin.names and isinstance(result.get("items"), list):
        plain_names(plugin.names, result["items"])
    output = finish(plugin, result, taken, round((time.monotonic() - started) * 1000))
    folder = store.data_dir(plugin.id)
    store.write_json(folder / "output.json", output)
    keep_history(plugin, output, folder)
    return output


def enabled(plugin) -> bool:
    """Whether a plugin runs. Your switch on the page decides. Until you've
    touched it, the plugin's own `enabled:` does."""
    settings = store.read_json(store.settings_path(plugin.id), {})
    choice = settings.get("enabled") if isinstance(settings, dict) else None
    return choice if isinstance(choice, bool) else plugin.enabled


class Scheduler:
    def __init__(self, workers: int = 4):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="shire-plugin")
        self.running: dict[str, Future] = {}
        self.last: dict[str, tuple[float, dict]] = {}  # when each last started, and with which settings

    def tick(self, now: float | None = None) -> list[Future]:
        """Starts every plugin that's due, and gives back what it started."""
        now = time.time() if now is None else now
        for plugin_id, future in list(self.running.items()):
            if future.done():
                del self.running[plugin_id]
                if future.exception():
                    print(f"shire: {plugin_id} couldn't be saved: {future.exception()}", file=sys.stderr)
        started = []
        for plugin in plugins.find().values():
            if plugin.id in self.running:
                continue
            if not enabled(plugin):
                self.last.pop(plugin.id, None)  # so it runs at once when it's switched back on
                continue
            when, config = self.last.get(plugin.id, (None, None))
            if when is None or config != plugin.config or now - when >= plugin.every:
                self.last[plugin.id] = (now, plugin.config)
                self.running[plugin.id] = self.pool.submit(run, plugin)
                started.append(self.running[plugin.id])
        return started

    def once(self) -> dict[str, dict]:
        """Runs every plugin that's on, once, and waits for them all."""
        futures = {pid: self.pool.submit(run, p) for pid, p in plugins.find().items() if enabled(p)}
        return {pid: future.result() for pid, future in futures.items()}

    def forever(self, stop: threading.Event, every: float = 5.0) -> None:
        while not stop.is_set():
            self.tick()
            stop.wait(every)

    def close(self) -> None:
        self.pool.shutdown(wait=True)
