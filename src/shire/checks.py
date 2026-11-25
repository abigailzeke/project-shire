"""The checks a plugin can ask for.

Five are built in, so a plugin that uses one needs nothing but its
plugin.yaml: website, program, port, file and folder. The sixth, script,
runs a program from the plugin's folder, for anything the five can't do.

A script can be in any language. Shire hands it one JSON object on standard
input, {"plugin", "name", "options"}, and it prints what it found in the
standard format. It runs as its own process with a time limit, so a script
that hangs or crashes is stopped and reported, and nothing else waits for it.
A script ending in .py runs with Shire's own Python, so it can `import shire`.

Every check gives back {"ok", "reason", "summary", "items"}, with only items
needed. The scheduler adds the rest."""

from __future__ import annotations

import fnmatch
import heapq
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import fmt, host

MAX_BYTES = 1_000_000
RECENT = 8


class Broken(Exception):
    """The plugin itself went wrong. The message goes onto the page."""


def _nothing(reason: str) -> dict:
    """What it watches isn't there, which isn't a fault."""
    return {"ok": False, "reason": reason, "items": []}


def _path(plugin, what: str):
    given = plugin.config.get("path")
    if not given:
        return None, _nothing(f"Name a {what}: add `path: ~/your/{what}` to this plugin's plugin.yaml in your space.")
    path = Path(str(given)).expanduser()
    there = path.is_file() if what == "file" else path.is_dir()
    return (path, None) if there else (None, _nothing(f"There's no {what} at {given}."))


# ------------------------------------------------------------------ website

def website(plugin) -> dict:
    """Whether a page answers, and how fast."""
    url = plugin.config["url"]
    item = {"key": "website", "name": plugin.name, "facts": {"Address": url}}
    started = time.monotonic()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "project-shire"})
        with urllib.request.urlopen(request, timeout=plugin.timeout) as answer:
            code = answer.status
    except urllib.error.HTTPError as e:
        code = e.code
    except (urllib.error.URLError, OSError, ValueError) as e:
        why = getattr(e, "reason", None) or e
        return {"items": [{**item, "value": "down", "state": "bad", "note": f"It didn't answer: {why}."}]}
    took = round((time.monotonic() - started) * 1000)
    item["facts"]["Answer"] = code
    if code < 400:
        return {"items": [{**item, "value": took, "unit": "ms", "state": "good"}]}
    return {"items": [{**item, "value": f"error {code}", "state": "warn" if code < 500 else "bad",
                       "note": f"It answered, but with error {code}."}]}


# ------------------------------------------------------------------ program

def program(plugin) -> dict:
    """Whether a program is running, found by a pattern in its command line."""
    try:
        pattern = re.compile(plugin.config["match"])
    except re.error as e:
        raise Broken(f"plugin.yaml: match isn't a pattern Shire can read ({e}).") from e
    mine = [p for p in host.processes() if p["pid"] != os.getpid() and pattern.search(p["args"])]
    item = {"key": "program", "name": plugin.name}
    if not mine:
        return {"items": [{**item, "value": "not running", "state": "bad"}]}
    return {"items": [{**item, "value": "running", "state": "good", "facts": {
        "Processes": len(mine),
        "Running for": fmt.dur(max(p["uptime"] for p in mine)),
        "Memory": fmt.size(sum(p["rss"] for p in mine)),
    }}]}


# --------------------------------------------------------------------- port

def port(plugin) -> dict:
    """Whether something is listening on a port."""
    where, number = plugin.config.get("host", "127.0.0.1"), plugin.config["port"]
    item = {"key": "port", "name": plugin.name, "facts": {"Address": f"{where}:{number}"}}
    try:
        with socket.create_connection((where, number), timeout=min(plugin.timeout, 5)):
            pass
    except OSError:
        return {"items": [{**item, "value": "closed", "state": "bad"}]}
    return {"items": [{**item, "value": "listening", "state": "good"}]}


# --------------------------------------------------------------------- file

def _value(v):
    if isinstance(v, bool):
        return "yes" if v else "no"
    return v if v is None or isinstance(v, (str, int, float)) else None


def file(plugin) -> dict:
    """What a file says. A JSON file already in the standard format is shown
    as it is, any other JSON object becomes one item for each of its keys,
    and anything else is shown as text."""
    path, nothing = _path(plugin, "file")
    if nothing:
        return nothing
    if path.stat().st_size > MAX_BYTES:
        raise Broken("The file is larger than 1 MB.")
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except ValueError as e:
            raise Broken("The file isn't valid JSON.") from e
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return {k: data[k] for k in ("ok", "reason", "summary", "items") if k in data}
        if isinstance(data, dict):
            items = []
            for key, v in list(data.items())[:500]:
                item = {"key": str(key), "name": str(key), "value": _value(v)}
                if isinstance(v, (dict, list)):
                    item["note"] = json.dumps(v, ensure_ascii=False)[:4000]
                items.append(item)
            return {"items": items}
    return {"items": [{"key": "file", "name": path.name, "note": text.strip()[:4000],
                       "facts": {"Changed": fmt.when(path.stat().st_mtime)}}]}


# ------------------------------------------------------------------- folder

def folder(plugin) -> dict:
    """How many files a folder holds, and which changed most recently.
    Hidden files and folders are left out."""
    path, nothing = _path(plugin, "folder")
    if nothing:
        return nothing
    pattern = plugin.config.get("pattern", "*")
    deadline = time.monotonic() + plugin.timeout
    count, seen = 0, []
    for root, dirs, names in os.walk(path):
        if time.monotonic() > deadline:
            raise Broken(f"The folder took longer than {plugin.timeout} s to read, so it was stopped.")
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            if name.startswith(".") or not fnmatch.fnmatch(name, pattern):
                continue
            count += 1
            full = os.path.join(root, name)
            try:
                seen.append((os.path.getmtime(full), full))
            except OSError:
                pass
    items = [{"key": "files", "name": "Files", "value": count}]
    for changed, full in heapq.nlargest(RECENT, seen):
        inside = os.path.relpath(full, path)
        item = {"key": f"file:{inside}", "name": Path(full).stem, "section": "Changed recently",
                "value": fmt.when(changed)}
        if os.path.dirname(inside):
            item["facts"] = {"Folder": os.path.dirname(inside)}
        items.append(item)
    return {"summary": f"{count} files", "items": items}


# ------------------------------------------------------------------- script

def _stop(process) -> None:
    """Stops a script and anything it started."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def script(plugin) -> dict:
    """Runs the plugin's own program and reads what it prints."""
    named = plugin.config["script"]
    if isinstance(named, dict):
        named = named.get(host.SYSTEM)
        if not named:
            return _nothing(f"It doesn't work on {host.SYSTEM_NAME} yet.")
    path = next((f / named for f in plugin.folders if (f / named).is_file()), None)
    if not path:
        raise Broken(f"plugin.yaml names the script {named}, and it isn't in the plugin's folder.")
    command = [sys.executable, str(path)] if path.suffix == ".py" else [str(path)]
    event = json.dumps({"plugin": plugin.id, "name": plugin.name, "options": plugin.config.get("options", {})})
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, cwd=path.parent, start_new_session=True)
    except PermissionError as e:
        raise Broken(f"Its script can't be run. Make it executable: chmod +x {path.name}") from e
    except OSError as e:
        raise Broken(f"Its script can't be run: {e.strerror}.") from e
    try:
        out, err = process.communicate(event, timeout=plugin.timeout)
    except subprocess.TimeoutExpired:
        _stop(process)
        raise Broken(f"It took longer than {plugin.timeout} s, so it was stopped.") from None
    if process.returncode != 0:
        last = (err.strip().splitlines() or ["it gave no message"])[-1]
        raise Broken(f"Its script stopped with an error: {last[:300]}")
    if len(out) > MAX_BYTES:
        raise Broken("Its script printed more than 1 MB.")
    try:
        result = json.loads(out)
    except ValueError:
        raise Broken("Its script didn't print JSON.") from None
    if not isinstance(result, dict):
        raise Broken("Its script should print one JSON object.")
    return result


CHECKS = {"website": website, "program": program, "port": port, "file": file, "folder": folder, "script": script}


def run(plugin) -> dict:
    """What the plugin found, or why it couldn't look. It never raises, so
    one plugin's trouble stays its own."""
    if plugin.problem:
        return {"ok": False, "error": plugin.problem, "items": []}
    try:
        return CHECKS[plugin.check](plugin)
    except Broken as e:
        return {"ok": False, "error": str(e), "items": []}
    except Exception as e:  # a fault in a check mustn't reach the scheduler
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "items": []}
