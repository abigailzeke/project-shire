"""Running apps, on macOS.

Two kinds of thing, both read from the list of processes:

- Apps: anything running from inside a .app. An app is open when its own
  program runs, and in the background when only its helpers or widgets do.
- Background helpers: programs from other companies that run outside any app,
  like device management, VPN tunnels and audio drivers. Anything younger
  than two minutes is left out, because it's mostly passing commands.

Each item's key is the app's or program's name, so your names and choices
survive a restart."""

import os
import re

from shire import fmt, host, script

HOME = os.path.expanduser("~")
APP = re.compile(r"^(?:/Applications|/System/Applications|/System/Volumes/Preboot/Cryptexes/App/System/Applications|"
                 + re.escape(HOME) + r"/Applications)/(?:[^/]+/)*?([^/]+)\.app/")
MAIN_PROGRAM = re.compile(r"/Contents/MacOS/(.+?)(?:\s+-|$)")
OTHER_COMPANY = re.compile(
    r"^(?:Contents/|Core Audio Driver \((?!Apple)|[A-Z0-9]{10}\.(?!com\.apple)|(?!com\.apple)[a-z0-9-]+\.[a-z0-9-]+\.[a-z0-9.-]+)")
YOUNG = 120


def add(group, name, p):
    g = group.setdefault(name, {"processes": 0, "cpu": 0.0, "mem": 0, "uptime": 0, "open": False})
    g["processes"] += 1
    g["cpu"] += p["cpu"]
    g["mem"] += p["rss"]
    g["uptime"] = max(g["uptime"], p["uptime"])
    return g


def facts(g, **more):
    return {"Processes": g["processes"], "Memory": fmt.size(g["mem"]), "CPU": f"{g['cpu']:.1f}%",
            "Running for": fmt.dur(g["uptime"]), **more}


def main():
    rows = host.processes()
    by_pid = {p["pid"]: p for p in rows}
    apps, others, started_by = {}, {}, {}

    for p in rows:
        args = p["args"]
        m = APP.match(args)
        if m:
            g = add(apps, m.group(1), p)
            # The app itself is open when its own program runs, not only a
            # widget, extension or helper from inside its bundle.
            rest = args[m.end():]
            inside = rest.split(" -")[0]
            if rest.startswith("Contents/MacOS/") and ".app/" not in inside and ".appex/" not in inside:
                g["open"] = True
            continue
        if p["uptime"] < YOUNG:
            continue
        first = args.split(" ")[0]
        if first.startswith("/"):
            if not first.startswith("/Library/") or first.startswith("/Library/Apple/"):
                continue
            main_program = MAIN_PROGRAM.search(args)
            name = main_program.group(1).strip() if main_program else os.path.basename(first)
        elif OTHER_COMPANY.match(args):
            name = args if args.startswith("Core Audio Driver") else os.path.basename(first)
        else:
            continue
        name = name[:120] or "unnamed"
        add(others, name, p)
        parent = by_pid.get(p["ppid"])
        if p["ppid"] == 1:
            started_by[name] = "launchd"
        elif parent:
            in_app = APP.match(parent["args"])
            started_by[name] = in_app.group(1) if in_app else os.path.basename(parent["args"].split(" ")[0])

    items = []
    for name, g in sorted(apps.items(), key=lambda kv: (not kv[1]["open"], -kv[1]["mem"])):
        item = {"key": name, "name": name, "section": "Apps",
                "value": "open" if g["open"] else "in the background", "facts": facts(g)}
        if not g["open"]:
            item["note"] = f"Only {name}'s helpers or widgets are running, not the app itself."
        items.append(item)
    for name, g in sorted(others.items(), key=lambda kv: -kv[1]["mem"]):
        items.append({"key": f"program:{name}", "name": name, "section": "Background helpers", "value": "running",
                      "facts": facts(g, **{"Started by": started_by.get(name, "unknown")})})

    opened = sum(1 for g in apps.values() if g["open"])
    script.done(items, f"{opened} open · {len(apps) - opened} in the background · {len(others)} background helpers")


main()
