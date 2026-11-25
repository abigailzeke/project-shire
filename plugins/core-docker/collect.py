"""Docker: every container, gathered by its compose project, with its health.
Docker works the same on any system, so this script does too.

A project is good when every part is up and healthy, warn when some are, and
bad when none is. A one-off that finished cleanly isn't counted against it.
A project's key is its compose name, and a lone container's is its own name."""

import json
import shutil

from shire import host, script


def main():
    if not shutil.which("docker"):
        return script.nothing("Docker isn't installed.")
    listed = host.run(["docker", "ps", "-a", "--format", "{{json .}}"], timeout=6)
    if not listed.strip():
        if not host.run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=6).strip():
            return script.nothing("Docker isn't running. Open Docker Desktop.")
        return script.done([], "No containers")
    usage = {}
    for line in host.run(["docker", "stats", "--no-stream", "--format", "{{json .}}"], timeout=10).splitlines():
        try:
            s = json.loads(line)
            usage[s.get("Name")] = (s.get("CPUPerc"), s.get("MemUsage"))
        except ValueError:
            pass

    projects, order = {}, []
    for line in listed.splitlines():
        try:
            c = json.loads(line)
        except ValueError:
            continue
        labels = dict(kv.split("=", 1) for kv in (c.get("Labels") or "").split(",") if "=" in kv)
        name, state, status = str(c.get("Names") or "unnamed"), c.get("State"), str(c.get("Status") or "")
        finished = state == "exited" and "Exited (0)" in status
        healthy = state == "running" and "unhealthy" not in status and "starting" not in status
        part = {"key": name[:300], "name": (labels.get("com.docker.compose.service") or name)[:200], "value": status or state}
        if not finished:
            part["state"] = "good" if healthy else "warn" if state == "running" else "bad"
        cpu, mem = usage.get(name, (None, None))
        part["facts"] = {k: v for k, v in {"Container": name, "Image": c.get("Image"), "Ports": c.get("Ports") or None,
                                           "CPU": cpu, "Memory": mem}.items() if v}
        project = labels.get("com.docker.compose.project")
        key = project or name
        if key not in projects:
            projects[key] = {"project": bool(project), "parts": []}
            order.append(key)
        projects[key]["parts"].append(part)

    items, up_count = [], 0
    for key in sorted(order):
        parts = projects[key]["parts"]
        if not projects[key]["project"]:
            items.append(parts[0])
            up_count += parts[0].get("state") == "good"
            continue
        counted = [p for p in parts if "state" in p]
        up = sum(1 for p in counted if p["state"] == "good")
        item = {"key": key[:300], "name": key[:200], "items": parts, "facts": {"Parts": len(parts)}}
        if not counted:
            item["value"] = "finished"
        elif up == len(counted):
            item.update(value="up", state="good")
        elif up:
            item.update(value=f"{up} of {len(counted)} up", state="warn")
        else:
            item.update(value="down", state="bad")
        up_count += item.get("state") == "good"
        items.append(item)
    script.done(items, f"{up_count} of {len(items)} up")


main()
