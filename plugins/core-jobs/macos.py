"""Background services, on macOS: every launchd job (yours, the ones apps
installed for every user, and the system's) and your crontab.

System daemons aren't in `launchctl list` without root, so whether one is
running comes from the list of processes. A job's key is its label."""

import glob
import os
import plistlib
import re

from shire import fmt, host, script

HOME = os.path.expanduser("~")
PLACES = [
    (os.path.join(HOME, "Library", "LaunchAgents"), "Yours"),
    ("/Library/LaunchAgents", "For every user"),
    ("/Library/LaunchDaemons", "System"),
]
DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def plain(label):
    """A readable name from a label like com.you.backup-files."""
    tail = re.sub(r"^(com|io|org|net|dev|us)\.[^.]+\.", "", re.sub(r"^local\.", "", label))
    tail = re.sub(r"[-_.]+", " ", tail).strip() or label
    return tail[0].upper() + tail[1:]


def schedule(d):
    bits = []
    if "StartInterval" in d:
        s = int(d["StartInterval"])
        bits.append(f"every {s // 3600} h" if s >= 3600 and s % 3600 == 0 else
                    f"every {s // 60} min" if s >= 60 and s % 60 == 0 else f"every {s} s")
    cal = d.get("StartCalendarInterval")
    for c in (cal if isinstance(cal, list) else [cal]) if cal else []:
        when = ""
        if "Weekday" in c:
            when += DAYS[int(c["Weekday"])] + " "
        if "Day" in c:
            when += f"day {c['Day']} "
        if "Hour" in c:
            when += f"{int(c['Hour']):02d}:{int(c.get('Minute', 0)):02d}"
        elif "Minute" in c:
            when += f"at :{int(c['Minute']):02d} past each hour"
        bits.append(("daily " if not ("Weekday" in c or "Day" in c) and "Hour" in c else "") + when.strip())
    if d.get("WatchPaths"):
        bits.append("when a file changes")
    if d.get("KeepAlive"):
        bits.append("always running")
    if d.get("RunAtLoad"):
        bits.append("at login")
    return " · ".join(bits) or "on demand"


def last_line(log):
    try:
        with open(log, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 2048))
            tail = [line for line in f.read().decode("utf-8", "replace").splitlines() if line.strip()]
        return fmt.tidy_args(tail[-1], 140) if tail else None
    except OSError:
        return None


def main():
    rows = host.processes()
    listed = {}
    for line in host.run(["launchctl", "list"]).splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 3:
            listed[parts[2]] = {"pid": None if parts[0] == "-" else int(parts[0]),
                                "exit": int(parts[1]) if parts[1].lstrip("-").isdigit() else None}
    items, seen, running_count, timers = [], set(), 0, 0
    for folder, whose in PLACES:
        for path in sorted(glob.glob(os.path.join(folder, "*.plist"))):
            try:
                with open(path, "rb") as f:
                    d = plistlib.load(f)
            except Exception:
                continue
            label = str(d.get("Label") or os.path.basename(path)[:-6])
            if label in seen:
                continue
            seen.add(label)
            program = d.get("ProgramArguments") or ([d["Program"]] if d.get("Program") else [])
            program = [str(a) for a in program]
            log = d.get("StandardOutPath") or d.get("StandardErrorPath")
            state = listed.get(label)
            system = whose == "System"
            running = bool(state and state["pid"])
            if system and program:
                running = any(p["args"].startswith(program[0]) for p in rows)
            timer = "StartInterval" in d or "StartCalendarInterval" in d
            loaded = system or state is not None
            item = {"key": label[:300], "name": plain(label)[:200], "section": whose}
            if item["name"] != label:
                item["original"] = label[:300]
            if d.get("Disabled"):
                item["value"] = "switched off"
            elif running:
                item["value"] = "running"
            elif not loaded:
                item.update(value="not loaded", note="launchd hasn't loaded it, so it won't run.")
            else:
                item["value"] = "on a timer" if timer else "waiting"
            if whose == "Yours" and state and state["exit"] not in (None, 0) and not running:
                item.update(state="warn", note=f"Its last run ended with error {state['exit']}.")
            running_count += running
            timers += timer
            facts = {"Runs": schedule(d), "Label": label}
            if program:
                facts["Command"] = fmt.tidy_args(" ".join(program), 160)
            if log and os.path.exists(log):
                facts["Last wrote its log"] = fmt.when(os.path.getmtime(log))
                facts["Last line"] = last_line(log)
            if log:
                facts["Log"] = str(log).replace(HOME, "~")
            item["facts"] = facts
            items.append(item)
    for line in host.run(["crontab", "-l"]).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or f"cron:{line}"[:300] in seen:
            continue
        seen.add(f"cron:{line}"[:300])
        words = line.split(None, 5)
        when, command = (" ".join(words[:5]), words[5]) if len(words) == 6 else ("", line)
        items.append({"key": f"cron:{line}"[:300], "name": fmt.tidy_args(command, 80), "section": "Crontab",
                      "value": when or "scheduled", "facts": {"Line": fmt.tidy_args(line, 240)}})
    script.done(items, f"{running_count} running · {timers} on a timer")


main()
