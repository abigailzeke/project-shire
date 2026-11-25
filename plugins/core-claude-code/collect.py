"""Claude Code: its sessions and Remote Control, what each session started
(its MCP servers and scripts, found in the list of processes, so nobody has
to list them), its line to Anthropic, and the jobs it scheduled.

Jobs scheduled inside a session live only in that session's memory, so the
agent lists them in jobs.json in your space when it makes them. One shows
while its session is alive and, if it runs once, until its time."""

import glob
import os
import re
import shutil
import time

from shire import fmt, host, script, store

HOME = os.path.expanduser("~")
SETTLED = 120  # a child younger than this is a passing command, not a helper
SKIP_WORDS = {"tool", "run", "uvx", "exec", "x", "-y"}
# `claude mcp list` and the like are commands that pass, not sessions.
NOT_A_SESSION = {"mcp", "update", "doctor", "install", "config", "plugin", "plugins", "auth", "setup-token",
                 "migrate-installer"}


def installed():
    path = shutil.which("claude") or os.path.join(HOME, ".local", "bin", "claude")
    return os.path.exists(path)


def helper_name(args):
    """A helper's short name: its script or package, not the tool running it."""
    words = args.split()
    exe = os.path.basename(words[0]) if words else ""
    if exe in ("uv", "uvx", "npx", "npm", "pnpm", "bunx", "node", "bun", "deno") or exe.startswith("python"):
        for w in words[1:]:
            if not w.startswith("-") and w not in SKIP_WORDS:
                return os.path.basename(w.rstrip("/")) or w
    return exe or "unnamed"


def started_by(rows, session_pid):
    """A session's settled children, each with everything under it folded in."""
    children = {}
    for p in rows:
        children.setdefault(p["ppid"], []).append(p)
    helpers = {}
    for child in children.get(session_pid, []):
        if child["uptime"] < SETTLED or os.path.basename(child["args"].split(" ")[0]) == "caffeinate":
            continue
        family, todo = [], [child]
        while todo:
            q = todo.pop()
            family.append(q)
            todo += children.get(q["pid"], [])
        name = helper_name(child["args"])[:120]
        h = helpers.setdefault(name, {"mem": 0, "n": 0, "uptime": 0, "command": fmt.tidy_args(child["args"], 200)})
        h["mem"] += sum(q["rss"] for q in family)
        h["n"] += len(family)
        h["uptime"] = max(h["uptime"], child["uptime"])
    return [{"key": name, "name": name, "value": fmt.size(h["mem"]),
             "facts": {"Running for": fmt.dur(h["uptime"]), "Processes": h["n"], "Command": h["command"]}}
            for name, h in sorted(helpers.items(), key=lambda kv: -kv[1]["mem"])]


def started_in(by_pid, pid):
    """The app a session runs in: the nearest program at or above it that
    runs from inside a .app, like Terminal or Obsidian. None if there isn't one."""
    seen = set()
    while pid in by_pid and pid not in seen:
        seen.add(pid)
        inside = re.search(r"/([^/]+)\.app/", by_pid[pid]["args"])
        if inside:
            return inside.group(1)
        pid = by_pid[pid]["ppid"]
    return None


def session_keys(sessions):
    """A key for each session that survives a restart, so your name for it
    sticks: by how it was started, numbered from the oldest when there's more
    than one of a kind."""
    kinds = ["remote-control" if "--remote-control" in p["args"] else "app" if "stream-json" in p["args"] else "terminal"
             for p in sessions]
    keys, seen = [""] * len(sessions), {}
    for i in sorted(range(len(sessions)), key=lambda i: -sessions[i]["uptime"]):
        seen[kinds[i]] = seen.get(kinds[i], 0) + 1
        keys[i] = f"session:{kinds[i]}" + (f":{seen[kinds[i]]}" if seen[kinds[i]] > 1 else "")
    return keys


def last_active(project):
    """When a transcript was last written: the project's, or any project's."""
    folder = re.sub(r"[^A-Za-z0-9]", "-", os.path.expanduser(project)) if project else "*"
    times = [os.path.getmtime(f) for f in glob.glob(os.path.join(HOME, ".claude", "projects", folder, "*.jsonl"))]
    return max(times) if times else None


def scheduled(jobs_file):
    path = os.path.expanduser(jobs_file) if jobs_file else store.home() / "jobs.json"
    listed = store.read_json(path, [])
    items = []
    for j in listed if isinstance(listed, list) else []:
        if not isinstance(j, dict):
            continue
        try:
            os.kill(int(j.get("pid", 0)), 0)  # only checks that its session is still alive
        except Exception:
            continue
        if not j.get("recurring") and j.get("at", 0) < time.time() - 60:
            continue
        key = f"job:{j.get('id') or j.get('prompt')}"[:300]
        name = (str(j.get("prompt") or "A job").strip().splitlines() or ["A job"])[0][:80]
        facts = {"Runs": "again and again" if j.get("recurring") else "once"}
        if j.get("at"):
            facts["At"] = fmt.when(j["at"])
        items.append({"key": key, "name": name, "section": "Scheduled by the agent",
                      "value": str(j.get("cron") or ""), "facts": facts})
    return items


def main():
    options = script.options()
    if not installed():
        return script.nothing("Claude Code isn't installed on this computer.")
    rows = host.processes()
    by_pid = {p["pid"]: p for p in rows}
    sessions = []
    for p in rows:
        words = p["args"].split()
        if os.path.basename(words[0]) == "claude" and not (len(words) > 1 and words[1] in NOT_A_SESSION):
            sessions.append(p)
    remote = [re.search(r"--remote-control\s+(\S+)", p["args"]) for p in sessions]
    reachable = [m.group(1) for m in remote if m]

    n = len(sessions)
    active = last_active(options.get("project"))
    note = ("No session is running." if not n else f"{n} session{'s' if n != 1 else ''}") + (
        f" · last active {fmt.when(active)}" if active else "")
    items = [
        {"key": "agent", "name": "Claude Code", "value": "running" if n else "not running",
         "state": "good" if n else "warn", "note": note},
        {"key": "remote-control", "name": "Remote Control", "value": "on" if reachable else "off",
         "state": "good" if reachable else "warn",
         "note": f"Your phone can reach {', '.join(reachable)}." if reachable else "Your phone can't reach the agent."},
    ]
    online, ms = host.reach("api.anthropic.com")
    items.append({"key": "anthropic", "name": "Anthropic", "value": ms, "unit": "ms", "state": "good"} if online else
                 {"key": "anthropic", "name": "Anthropic", "value": "unreachable", "state": "bad",
                  "note": "This computer can't reach Anthropic."})

    for p, m, key in zip(sessions, remote, session_keys(sessions)):
        effort = re.search(r"--effort\s+(\S+)", p["args"])
        facts = {"Remote Control": m.group(1) if m else "off", "Process": p["pid"],
                 "Memory": fmt.size(p["rss"]), "CPU": f"{p['cpu']:.1f}%", "Command": fmt.tidy_args(p["args"])}
        if effort:
            facts["Effort"] = effort.group(1)
        app = started_in(by_pid, p["pid"])
        if app:
            facts["Started in"] = app
        name = (f"Remote Control · {m.group(1)}" if m else f"Session in {app}" if app
                else "Session in an app" if key.startswith("session:app") else "Session")
        item = {"key": key, "name": name,
                "section": "Sessions", "value": fmt.dur(p["uptime"]), "facts": facts}
        helpers = started_by(rows, p["pid"])
        if helpers:
            item["items"] = helpers
        items.append(item)

    items += scheduled(options.get("jobs_file"))
    script.done(items, note)


if __name__ == "__main__":
    main()
