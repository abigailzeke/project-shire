"""Connectors: what Claude Code can reach, from `claude mcp list`, which
checks each one live. A connector's key is the name Claude Code gives it."""

import os
import re
import shutil

from shire import fmt, host, script

HOME = os.path.expanduser("~")


def kind_and_name(name):
    kind = ("claude.ai connector" if name.startswith("claude.ai ")
            else f"{name.split(':')[1]} plugin" if name.startswith("plugin:") and name.count(":") >= 2
            else "On this computer")
    plain = re.sub(r"^plugin:[^:]+:", "", re.sub(r"^claude\.ai ", "", name)) or name
    return kind, plain[0].upper() + plain[1:]


def main():
    claude = shutil.which("claude") or os.path.join(HOME, ".local", "bin", "claude")
    if not os.path.exists(claude):
        return script.nothing("Claude Code isn't installed on this computer.")
    project = script.options().get("project")
    out = host.run([claude, "mcp", "list"], timeout=80, cwd=os.path.expanduser(project) if project else HOME)
    items, seen, connected = [], set(), 0
    for line in out.splitlines():
        m = re.match(r"^(.+?): (.*?) - \S (.+)$", line.strip())
        if not m or m.group(1) in seen:
            continue
        name, target, status = m.group(1), m.group(2), m.group(3).strip()
        seen.add(name)
        target = re.sub(r"\s*\((?:HTTP|SSE|stdio)\)\s*$", "", target).strip()
        kind, plain = kind_and_name(name)
        good = status.lower().startswith("connected")
        connected += good
        item = {"key": name[:300], "name": plain[:200], "value": status[0].lower() + status[1:],
                "facts": {"Kind": kind, "Reaches": fmt.tidy_args(target, 160), "Claude Code calls it": name}}
        if good:
            item["state"] = "good"
        elif "auth" not in status.lower():  # one that's only waiting for you to sign in isn't broken
            item["state"] = "bad"
        items.append(item)
    script.done(items, f"{connected} of {len(items)} connected")


main()
