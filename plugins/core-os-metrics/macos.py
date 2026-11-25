"""Mac health, on macOS: one item for each thing worth knowing about the
computer itself, then its heaviest processes.

Everything is read with tools that come with macOS (pmset, ioreg, sysctl,
vm_stat, top) and never needs sudo or a permission prompt. If one reading
fails, the others still come through."""

import os
import re
import shutil
import tempfile
import time

from shire import fmt, host, script

GB = 1024 ** 3
HOME = os.path.expanduser("~")
APP = re.compile(r"^(?:/Applications|/System/Applications|/System/Volumes/Preboot/Cryptexes/App/System/Applications|"
                 + re.escape(HOME) + r"/Applications)/(?:[^/]+/)*?([^/]+)\.app/")
MAIN_PROGRAM = re.compile(r"/Contents/MacOS/(.+?)(?:\s+-|$)")
HOLD = re.compile(r"pid (\d+)\(([^)]+)\):\s*\[[^\]]+\]\s*([\d:]+)\s+(\w+)\s+named:\s*\"([^\"]*)\"(?:\s*\n\s*Details:\s*([^\n]+))?")


def sysctl(name):
    return host.run(["sysctl", "-n", name]).strip()


def number(text, default=0.0):
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


# -------------------------------------------------------------------- awake

def held_by(process, kind, name):
    """A plain name for whatever is holding the Mac awake."""
    if process == "caffeinate":
        return "Keep-awake"
    if process == "powerd" and re.search("display is on", name, re.I):
        return "Screen is on"
    if kind == "UserIsActive":
        return "You're using it"
    if "backupd" in process:
        return "Time Machine"
    return process


def awake(options):
    """Whether sleep is switched off, so the Mac keeps running with its lid
    shut, and everything holding it awake right now."""
    settings = host.run(["pmset", "-g"])
    sleep_off = bool(re.search(r"SleepDisabled\s+1", settings))
    low_power = bool(re.search(r"lowpowermode\s+1", settings))
    lid = re.search(r'"AppleClamshellState" = (Yes|No)', host.run(["ioreg", "-r", "-k", "AppleClamshellState", "-d", "1"]))
    shut = (lid.group(1) == "Yes") if lid else None
    listed = host.run(["pmset", "-g", "assertions"]).split("Listed by owning process:")[-1].split("Kernel Assertions:")[0]
    holds = {}
    for m in HOLD.finditer(listed):
        process, held, kind, name, details = m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
        key = f"{process}:{kind}:{name}"[:300]
        facts = {"Program": process, "Kind": kind, "Reason": name}
        if details:
            facts["Details"] = fmt.tidy_args(details.strip(), 200)
        holds.setdefault(key, {"key": key, "name": held_by(process, kind, name), "value": held, "facts": facts})
    item = {
        "key": "awake", "name": "Awake", "value": "on" if sleep_off else "off",
        "state": "good" if sleep_off else "warn",
        "note": ("Sleep is switched off, so the Mac keeps running when its lid is shut." if sleep_off else
                 "Sleep is allowed, so the Mac sleeps when its lid shuts. To keep it awake: sudo pmset -a disablesleep 1"),
        "facts": {"Lid": "unknown" if shut is None else "shut" if shut else "open",
                  "Sleep": "switched off" if sleep_off else "allowed",
                  "Low power mode": "on" if low_power else "off"},
    }
    if holds:
        item["items"] = list(holds.values())
    return item


# -------------------------------------------------------------------- power

def power(options):
    """The battery's charge, whether the Mac is on power, and the battery's health."""
    out = host.run(["pmset", "-g", "batt"])
    m = re.search(r"(\d+)%;\s*([^;]+);\s*([^\s]+) remaining", out)
    if not m:
        return {"key": "power", "name": "Power", "value": "on power", "note": "This Mac has no battery."}
    percent, state = int(m.group(1)), m.group(2).strip()
    on_power = "AC Power" in out
    left = None
    if re.match(r"\d+:\d+", m.group(3)) and m.group(3) != "0:00":
        h, mi = m.group(3).split(":")
        left = (int(h) * 60 + int(mi)) * 60
    registry = host.run(["ioreg", "-rn", "AppleSmartBattery"])

    def key(name):
        k = re.search(r'^\s*"' + name + r'" = (\d+)', registry, re.M)
        return int(k.group(1)) if k else None

    raw_max, design, temp = key("AppleRawMaxCapacity"), key("DesignCapacity"), key("Temperature")
    health = round(100 * raw_max / design) if raw_max and design else None
    watts = re.search(r"Wattage = (\d+)W", host.run(["pmset", "-g", "ac"]))

    words = ("Charged" if state == "charged"
             else f"Charging{f', full in {fmt.dur(left)}' if left else ''}" if state == "charging"
             else (f"{fmt.dur(left)} left" if left else "On battery") if state == "discharging" else state)
    level = "good" if on_power or percent > 30 else "bad" if percent <= 15 else "warn"
    note = words + (" · on power" if on_power else "")
    if health is not None and health < 80:
        level = "warn" if level == "good" else level
        note += f" · the battery holds {health}% of what it did when new"
    facts = {"Charge": f"{percent}%", "State": state,
             "Charger": f"{watts.group(1)} W" if watts else ("on power" if on_power else "not plugged in")}
    if health is not None:
        facts["Health"] = f"{health}%"
    if key("CycleCount") is not None:
        facts["Cycles"] = key("CycleCount")
    if temp:
        facts["Temperature"] = f"{round(temp / 100, 1)}°C"
    return {"key": "power", "name": "Battery", "value": percent, "unit": "%", "state": level, "note": note, "facts": facts}


# -------------------------------------------------------------- temperature

def sensors():
    """The chip's, battery's and SSD's own temperature sensors, read through
    IOKit's HID event system: no sudo and no prompt."""
    try:
        import ctypes
        from ctypes import c_char_p, c_double, c_int32, c_int64, c_long, c_uint32, c_void_p
        iokit = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/IOKit.framework/IOKit")
        cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        utf8 = 0x08000100
        cf.CFStringCreateWithCString.restype = c_void_p
        cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
        cf.CFNumberCreate.restype = c_void_p
        cf.CFNumberCreate.argtypes = [c_void_p, ctypes.c_int, c_void_p]
        cf.CFDictionaryCreate.restype = c_void_p
        cf.CFDictionaryCreate.argtypes = [c_void_p, ctypes.POINTER(c_void_p), ctypes.POINTER(c_void_p), c_long, c_void_p, c_void_p]
        cf.CFArrayGetCount.restype = c_long
        cf.CFArrayGetCount.argtypes = [c_void_p]
        cf.CFArrayGetValueAtIndex.restype = c_void_p
        cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
        cf.CFStringGetCString.restype = ctypes.c_bool
        cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_long, c_uint32]
        iokit.IOHIDEventSystemClientCreate.restype = c_void_p
        iokit.IOHIDEventSystemClientCreate.argtypes = [c_void_p]
        iokit.IOHIDEventSystemClientSetMatching.argtypes = [c_void_p, c_void_p]
        iokit.IOHIDEventSystemClientCopyServices.restype = c_void_p
        iokit.IOHIDEventSystemClientCopyServices.argtypes = [c_void_p]
        iokit.IOHIDServiceClientCopyProperty.restype = c_void_p
        iokit.IOHIDServiceClientCopyProperty.argtypes = [c_void_p, c_void_p]
        iokit.IOHIDServiceClientCopyEvent.restype = c_void_p
        iokit.IOHIDServiceClientCopyEvent.argtypes = [c_void_p, c_int64, c_int32, c_int64]
        iokit.IOHIDEventGetFloatValue.restype = c_double
        iokit.IOHIDEventGetFloatValue.argtypes = [c_void_p, c_int32]

        def cfs(s):
            return cf.CFStringCreateWithCString(None, s.encode(), utf8)

        def cfn(i):
            v = c_int32(i)
            return cf.CFNumberCreate(None, 3, ctypes.byref(v))

        def callbacks(name):
            return ctypes.addressof(ctypes.c_char.in_dll(cf, name))

        keys = (c_void_p * 2)(cfs("PrimaryUsagePage"), cfs("PrimaryUsage"))
        vals = (c_void_p * 2)(cfn(0xff00), cfn(5))  # Apple's temperature sensors
        match = cf.CFDictionaryCreate(None, keys, vals, 2, callbacks("kCFTypeDictionaryKeyCallBacks"),
                                      callbacks("kCFTypeDictionaryValueCallBacks"))
        client = iokit.IOHIDEventSystemClientCreate(None)
        iokit.IOHIDEventSystemClientSetMatching(client, match)
        services = iokit.IOHIDEventSystemClientCopyServices(client)
        product = cfs("Product")
        chip, batt, ssd = [], [], []
        for i in range(cf.CFArrayGetCount(services) if services else 0):
            sc = cf.CFArrayGetValueAtIndex(services, i)
            p = iokit.IOHIDServiceClientCopyProperty(sc, product)
            buf = ctypes.create_string_buffer(128)
            name = buf.value.decode() if p and cf.CFStringGetCString(p, buf, 128, utf8) else ""
            ev = iokit.IOHIDServiceClientCopyEvent(sc, 15, 0, 0)  # 15: temperature
            if not ev:
                continue
            t = iokit.IOHIDEventGetFloatValue(ev, 15 << 16)
            if not 0 < t < 130:
                continue
            if "tdie" in name:
                chip.append(t)
            elif "battery" in name:
                batt.append(t)
            elif "NAND" in name:
                ssd.append(t)
        return chip, batt, ssd
    except Exception:
        return [], [], []


def temperature(options):
    """How warm the chip is. A Mac without a fan slows itself down when it's
    too hot, so the hottest chip sensor is the number that matters."""
    chip, batt, ssd = sensors()
    level = re.search(r"Thermal Warning Level\s*=\s*(\d+)", host.run(["pmset", "-g", "therm"]), re.I)
    slowing = bool(level and int(level.group(1)) > 0)
    if not chip:
        return {"key": "temperature", "name": "Temperature", "note": "No sensor reading.",
                **({"state": "warn", "value": "slowing down"} if slowing else {})}
    hottest = round(max(chip), 1)
    words = ("Slowing down to cool off" if slowing else "Cool" if hottest < 50 else "Warm" if hottest < 80
             else "Hot" if hottest < 95 else "Very hot")
    facts = {"Chip, hottest": f"{hottest}°C", "Chip, average": f"{round(sum(chip) / len(chip), 1)}°C",
             "Slowing down": "yes, to cool off" if slowing else "no", "Sensors": f"{len(chip)} on the chip"}
    if batt:
        facts["Battery"] = f"{round(sum(batt) / len(batt), 1)}°C"
    if ssd:
        facts["Storage"] = f"{round(max(ssd), 1)}°C"
    return {"key": "temperature", "name": "Temperature", "value": round(hottest), "unit": "°C",
            "state": "warn" if slowing or hottest >= 95 else "good", "note": words, "facts": facts}


# ------------------------------------------------------------------- memory

def memory(options):
    """Memory in use, counted the way Activity Monitor does, and macOS's own
    measure of whether it's running short."""
    total = int(number(sysctl("hw.memsize")))
    out = host.run(["vm_stat"])
    size = re.search(r"page size of (\d+)", out)
    page = int(size.group(1)) if size else 16384

    def pages(label):
        m = re.search(re.escape(label) + r":\s+(\d+)", out)
        return int(m.group(1)) * page if m else 0

    wired, compressed = pages("Pages wired down"), pages("Pages occupied by compressor")
    anonymous, purgeable = pages("Anonymous pages"), pages("Pages purgeable")
    apps = max(anonymous - purgeable, 0) if anonymous else pages("Pages active")
    used = apps + wired + compressed
    swap = re.search(r"used = ([\d.]+)M", sysctl("vm.swapusage"))
    pressure = {"1": "normal", "2": "warning", "4": "critical"}.get(sysctl("kern.memorystatus_vm_pressure_level"), "normal")
    return {
        "key": "memory", "name": "Memory", "value": round(100 * used / total) if total else None, "unit": "%",
        "state": {"normal": "good", "warning": "warn", "critical": "bad"}[pressure],
        "note": f"Pressure {pressure} · {round(total / GB)} GB",
        "facts": {"In use": f"{fmt.size(used)} of {fmt.size(total)}", "Apps": fmt.size(apps),
                  "Kept by macOS": fmt.size(wired), "Compressed": fmt.size(compressed),
                  "Cached files": fmt.size(pages("File-backed pages") + purgeable),
                  "Swap": fmt.size(int(float(swap.group(1)) * 1024 * 1024) if swap else 0), "Pressure": pressure},
    }


# ---------------------------------------------------------------- processor

def processor(options):
    """How busy the processor is, from two samples of top a second apart."""
    last = host.run(["top", "-l", "2", "-n", "0", "-s", "1"], timeout=8).split("Processes:")[-1]
    cpu = re.search(r"CPU usage:\s*([\d.]+)% user,\s*([\d.]+)% sys,\s*([\d.]+)% idle", last)
    counts = re.search(r"(\d+) total,\s*(\d+) running,.*?(\d+) threads", last)
    cores = int(number(sysctl("hw.ncpu")))
    load = [float(n) for n in re.findall(r"[\d.]+", sysctl("vm.loadavg"))[:3]]
    facts = {"Load": " · ".join(f"{v:.2f}" for v in load), "Cores": cores}
    if cpu:
        facts.update({"Apps and programs": f"{cpu.group(1)}%", "macOS": f"{cpu.group(2)}%"})
    if counts:
        facts.update({"Processes": int(counts.group(1)), "Threads": int(counts.group(3))})
    return {"key": "processor", "name": "Processor", "value": round(100 - float(cpu.group(3))) if cpu else None,
            "unit": "%", "note": f"{cores} cores" + (f" · {counts.group(1)} processes" if counts else ""), "facts": facts}


# ------------------------------------------------------------------ storage

def storage(options):
    """How full the disk is. On a Mac, your files live on the Data volume."""
    u = shutil.disk_usage("/System/Volumes/Data")
    return {"key": "storage", "name": "Storage", "value": round(u.free / GB), "unit": "GB free",
            "state": "warn" if u.free / u.total < 0.1 else "good",
            "note": f"{round(100 * (u.total - u.free) / u.total)}% of {round(u.total / GB)} GB used",
            "facts": {"Free": fmt.size(u.free), "Used": fmt.size(u.total - u.free), "Size": fmt.size(u.total)}}


# ------------------------------------------------------------------ network

def network(options):
    """Whether the Mac is online, its addresses, and Tailscale if it's on."""
    where, _, port = str(options.get("check") or "1.1.1.1:443").rpartition(":")
    ip = host.run(["ipconfig", "getifaddr", "en0"]).strip() or None
    route = host.run(["route", "-n", "get", "default"])
    router, interface = re.search(r"gateway:\s*(\S+)", route), re.search(r"interface:\s*(\S+)", route)
    online, ms = host.reach(where, int(port))
    # Tailscale gives the Mac an address in 100.64.0.0/10.
    ts = re.search(r"inet (100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+)", host.run(["ifconfig"]))
    kind = None if not ip else "iPhone hotspot" if ip.startswith("172.20.10.") else "Wi-Fi"
    note = " · ".join(filter(None, [kind or "No network", f"{ms} ms" if online else None, "Tailscale on" if ts else None]))
    return {"key": "network", "name": "Network", "value": "online" if online else "offline",
            "state": "good" if online else "bad", "note": note,
            "facts": {"Connection": kind or "none", "Address": ip, "Router": router.group(1) if router else None,
                      "Interface": interface.group(1) if interface else None,
                      "Answered in": f"{ms} ms" if online else "no answer", "Checked against": f"{where}:{port}",
                      "Tailscale": ts.group(1) if ts else "not connected"}}


# ----------------------------------------------------------------- this mac

def model():
    """The Mac's model name. system_profiler is slow, and the answer never
    changes, so it's asked once a day and kept in the temporary folder."""
    kept = os.path.join(tempfile.gettempdir(), "project-shire-model.txt")
    try:
        if time.time() - os.path.getmtime(kept) < 86400:
            with open(kept, encoding="utf-8") as f:
                return f.read().strip() or None
    except OSError:
        pass
    m = re.search(r"Model Name:\s*(.+)", host.run(["system_profiler", "SPHardwareDataType"], timeout=12))
    name = m.group(1).strip() if m else ""
    try:
        with open(kept, "w", encoding="utf-8") as f:
            f.write(name)
    except OSError:
        pass
    return name or None


def this_mac(options):
    """The Mac itself, and how long it's been running."""
    started = re.search(r"sec = (\d+)", sysctl("kern.boottime"))
    started = int(started.group(1)) if started else None
    system = "macOS " + host.run(["sw_vers", "-productVersion"]).strip()
    local = host.run(["scutil", "--get", "LocalHostName"]).strip()
    return {"key": "this-mac", "name": "This Mac",
            "value": fmt.dur(time.time() - started) if started else None, "note": f"Running · {system}",
            "facts": {"Name": host.run(["scutil", "--get", "ComputerName"]).strip(),
                      "Model": model() or sysctl("hw.model"), "Chip": sysctl("machdep.cpu.brand_string"),
                      "Memory": f"{round(number(sysctl('hw.memsize')) / GB)} GB", "System": system,
                      "Running since": fmt.when(started) if started else None,
                      "Network name": f"{local}.local" if local else None}}


# ---------------------------------------------------------------- processes

def heaviest(options, count=8):
    """The processes using the most memory, with an app's helpers counted as
    part of the app."""
    groups = {}
    for p in host.processes():
        args = p["args"]
        app, main = APP.match(args), MAIN_PROGRAM.search(args)
        name = (app.group(1) if app else main.group(1).strip() if main else os.path.basename(args.split(" ")[0]))[:120]
        g = groups.setdefault(name or "unnamed", {"mem": 0, "cpu": 0.0, "n": 0})
        g["mem"] += p["rss"]
        g["cpu"] += p["cpu"]
        g["n"] += 1
    top = sorted(groups.items(), key=lambda kv: -kv[1]["mem"])[:count]
    return [{"key": f"process:{name}", "name": name, "section": "Heaviest processes", "value": fmt.size(g["mem"]),
             "facts": {"CPU": f"{g['cpu']:.1f}%", "Processes": g["n"]}} for name, g in top]


READINGS = [("awake", "Awake", awake), ("power", "Battery", power), ("temperature", "Temperature", temperature),
            ("memory", "Memory", memory), ("processor", "Processor", processor), ("storage", "Storage", storage),
            ("network", "Network", network), ("this-mac", "This Mac", this_mac), ("processes", "Processes", heaviest)]


def main():
    options = script.options()
    items = []
    for key, name, read in READINGS:
        try:
            found = read(options)
            items += found if isinstance(found, list) else [found]
        except Exception as e:  # one reading failing mustn't lose the others
            items.append({"key": key, "name": name, "note": f"It couldn't be read: {type(e).__name__}: {e}"})
    script.done(items)


main()
