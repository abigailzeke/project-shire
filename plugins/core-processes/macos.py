"""Heaviest processes, on macOS: the processes using the most memory, with
an app's helpers counted as part of the app.

Each item's key is the app's or program's name, so your names and choices
survive a restart."""

import os
import re

from shire import fmt, host, script

HOME = os.path.expanduser("~")
APP = re.compile(r"^(?:/Applications|/System/Applications|/System/Volumes/Preboot/Cryptexes/App/System/Applications|"
                 + re.escape(HOME) + r"/Applications)/(?:[^/]+/)*?([^/]+)\.app/")
MAIN_PROGRAM = re.compile(r"/Contents/MacOS/(.+?)(?:\s+-|$)")
COUNT = 8


def main():
    groups = {}
    for p in host.processes():
        args = p["args"]
        app, main = APP.match(args), MAIN_PROGRAM.search(args)
        name = (app.group(1) if app else main.group(1).strip() if main else os.path.basename(args.split(" ")[0]))[:120]
        g = groups.setdefault(name or "unnamed", {"mem": 0, "cpu": 0.0, "n": 0})
        g["mem"] += p["rss"]
        g["cpu"] += p["cpu"]
        g["n"] += 1
    top = sorted(groups.items(), key=lambda kv: -kv[1]["mem"])[:COUNT]
    items = [{"key": f"process:{name}", "name": name, "value": fmt.size(g["mem"]),
              "facts": {"CPU": f"{g['cpu']:.1f}%", "Processes": g["n"]}} for name, g in top]
    script.done(items, f"{top[0][0]} uses the most" if top else "No processes found")


main()
