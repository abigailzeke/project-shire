"""Running scripts, on macOS: Python, Node, uv and the like, and anything run
from the home folder or Homebrew. A script's children are folded into it.

Two kinds are left out: anything younger than two minutes, which is mostly
passing commands, and anything started by a program in `leave_to`, which that
program's own plugin shows.

Each script's key is its file path, so your names and choices survive a restart."""

import os
import re

from shire import fmt, host, script

HOME = os.path.expanduser("~")
APP = re.compile(r"^(?:/Applications|/System/Applications|/System/Volumes/Preboot/Cryptexes/App/System/Applications|"
                 + re.escape(HOME) + r"/Applications)/(?:[^/]+/)*?([^/]+)\.app/")
SCRIPT_EXE = re.compile(r"^(python[\d.]*|Python|node|uv|uvx|bun|deno|ruby|perl|php|java|bash|sh|zsh|npm|npx|pnpm)$")
SCRIPT_FILE = re.compile(r"(\S+\.(?:py|js|mjs|cjs|ts|sh|rb|pl|php))(?=\s|$)")
SKIP_WORDS = {"tool", "run", "uvx", "exec", "x"}
USER_PLACES = (HOME + "/", "/opt/homebrew/", "/usr/local/")
YOUNG = 120


def exe_of(p):
    return os.path.basename(p["args"].split(" ")[0])


def identity(args):
    """(key, name): the script's file path and file name, or for a tool run
    without a file, the tool and its first word."""
    m = SCRIPT_FILE.search(args)
    if m:
        return fmt.tidy_args(m.group(1)), os.path.basename(m.group(1))
    words = args.split()
    exe = os.path.basename(words[0]) if words else ""
    name = exe
    if SCRIPT_EXE.match(exe):
        name = next((os.path.basename(w.rstrip("/")) or w for w in words[1:]
                     if not w.startswith("-") and w not in SKIP_WORDS), exe)
    return (f"{exe} {name}" if name != exe else exe), name


def main():
    leave_to = set(script.options().get("leave_to") or [])
    rows = host.processes()
    by_pid = {p["pid"]: p for p in rows}

    def ancestors(p):
        seen = set()
        q = by_pid.get(p["ppid"])
        while q and q["pid"] not in seen:
            seen.add(q["pid"])
            yield q
            if q["pid"] <= 1:
                break
            q = by_pid.get(q["ppid"])

    picked = {}
    for p in rows:
        if APP.match(p["args"]):
            continue
        exe = exe_of(p)
        if exe in leave_to or exe == "caffeinate":
            continue
        if exe in ("zsh", "bash", "sh") and (p["args"].startswith("-") or len(p["args"].split()) == 1):
            continue
        if any(exe_of(q) in leave_to for q in ancestors(p)):
            continue
        if SCRIPT_EXE.match(exe) or p["args"].split(" ")[0].startswith(USER_PLACES):
            picked[p["pid"]] = p

    families = {}
    for p in picked.values():
        root = p
        for q in ancestors(p):
            if q["pid"] in picked:
                root = q
        families.setdefault(root["pid"], []).append(p)

    found = {}
    for pid, members in families.items():
        root = by_pid[pid]
        if root["uptime"] < YOUNG:
            continue
        started = "something that has since closed"
        for q in ancestors(root):
            app = APP.match(q["args"])
            if app:
                started = app.group(1)
                break
            if q["pid"] == 1:
                started = "launchd"
                break
        key, name = identity(root["args"])
        s = found.setdefault(key[:300], {"name": name[:120] or "unnamed", "copies": 0, "processes": 0, "cpu": 0.0,
                                         "mem": 0, "uptime": 0, "started": started,
                                         "command": fmt.tidy_args(root["args"], 240)})
        s["copies"] += 1
        s["processes"] += len(members)
        s["cpu"] += sum(m["cpu"] for m in members)
        s["mem"] += sum(m["rss"] for m in members)
        s["uptime"] = max(s["uptime"], root["uptime"])

    items = []
    for key, s in sorted(found.items(), key=lambda kv: -kv[1]["mem"]):
        facts = {"Started by": s["started"], "Memory": fmt.size(s["mem"]), "CPU": f"{s['cpu']:.1f}%",
                 "Running for": fmt.dur(s["uptime"]), "Processes": s["processes"], "Command": s["command"]}
        if s["copies"] > 1:
            facts["Copies running"] = s["copies"]
        items.append({"key": key, "name": s["name"], "value": "running", "facts": facts})
    script.done(items, f"{len(items)} running")


main()
