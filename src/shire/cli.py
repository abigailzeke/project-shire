"""The shire command.

    shire run          runs Shire here, until you stop it
    shire run --once   runs every plugin once and shows what each found
    shire start        keeps Shire running, and starts it with your Mac
    shire stop         stops it, and stops it starting by itself
    shire link         prints the link to open on your phone
"""

from __future__ import annotations

import argparse
import os
import plistlib
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import __version__, host, plugins, server, store
from .scheduler import Scheduler

PORT = 5190
EVERYWHERE = "0.0.0.0"  # every network this computer is on
LABEL = "io.github.abigailzeke.shire"  # what launchd calls it
LOG = "~/Library/Logs/project-shire.log"
BIND_TRIES = 10


def _once() -> int:
    scheduler = Scheduler()
    outputs = scheduler.once()
    scheduler.close()
    found = plugins.find()
    width = max((len(plugin_id) for plugin_id in found), default=0)
    for plugin_id in found:
        out = outputs.get(plugin_id)
        if out is None:
            line = "off"
        elif out.get("error"):
            line = f"error    {out['error']}"
        elif not out["ok"]:
            line = f"nothing  {out.get('reason', '')}"
        else:
            line = f"ok       {len(out['items'])} items in {out['took_ms'] / 1000:.1f} s"
        print(f"{plugin_id:<{width}}  {line}")
    return 1 if any(out.get("error") for out in outputs.values()) else 0


def _running() -> dict | None:
    """What a running Shire wrote down about itself, if it's still alive."""
    found = store.read_json(store.server_path())
    try:
        os.kill(int(found["pid"]), 0)  # only checks that it's there
        return found if isinstance(found.get("port"), int) else None
    except (TypeError, KeyError, ValueError, OSError):
        return None


def _run(where: str, port: int) -> int:
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    web = None
    for attempt in range(BIND_TRIES):  # a Shire that's just been stopped takes a moment to let go of the port
        try:
            web = server.listen(where, port)
            break
        except OSError as e:
            if attempt == BIND_TRIES - 1:
                print(f"Shire can't use port {port}: {e.strerror or e}. If Shire is already running, stop that one "
                      f"first, or pick another port with --port.", file=sys.stderr)
                return 1
            time.sleep(0.5)
    store.key()  # made now if there isn't one, so `shire link` has it
    threading.Thread(target=web.run, name="shire-server", daemon=True).start()
    store.write_json(store.server_path(), {"pid": os.getpid(), "port": port, "host": where, "started": int(time.time())})
    print(f"Shire is running on port {port}. Your space is {store.home()}. "
          f"`shire link` prints the link for your phone. Stop it with Ctrl-C.", flush=True)
    scheduler = Scheduler()
    scheduler.forever(stop)
    scheduler.close()
    store.server_path().unlink(missing_ok=True)  # the server's thread ends with the program
    return 0


def _link() -> int:
    live = _running()
    port = live["port"] if live else PORT
    where = live.get("host") if live else EVERYWHERE
    if live:
        print("Open one of these on your phone, once. The phone remembers you for a year.\n")
    else:
        print("Shire isn't running. Start it with `shire start`, and then one of these will open:\n")
    here = ("This computer", "localhost")
    places = host.addresses() + [here] if where == EVERYWHERE else [here if where == "127.0.0.1" else ("This computer", where)]
    width = max(len(name) for name, _ in places)
    key = store.key()
    for name, address in places:
        print(f"  {name:<{width}}  http://{address}:{port}/?key={key}")
    print("\nThe link holds your key, so don't share it.")
    return 0


def _plist() -> Path:
    return Path("~/Library/LaunchAgents").expanduser() / f"{LABEL}.plist"


def _launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _start(where: str, port: int) -> int:
    """Hands Shire to launchd, which keeps it running and starts it again
    when the Mac does."""
    if host.SYSTEM != "macos":
        print("`shire start` works on a Mac for now. Here, `shire run` runs Shire until you stop it.")
        return 1
    log = Path(LOG).expanduser()
    env = {"PATH": host.full_path()}
    if os.environ.get("SHIRE_HOME"):
        env["SHIRE_HOME"] = os.environ["SHIRE_HOME"]
    job = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "shire", "run", "--port", str(port), "--host", where],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
        "EnvironmentVariables": env,
    }
    path, domain = _plist(), f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{LABEL}")  # the one from before, if there is one
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(job, f)
    for _ in range(10):  # launchd needs a moment to let go of the one from before
        result = _launchctl("bootstrap", domain, str(path))
        if result.returncode == 0:
            break
        time.sleep(0.5)
    else:
        print(f"launchd wouldn't take it: {(result.stderr or result.stdout).strip()}", file=sys.stderr)
        return 1
    for _ in range(20):
        if _running():
            break
        time.sleep(0.5)
    else:
        print(f"Shire was handed to launchd but hasn't come up. Its log is {log}.", file=sys.stderr)
        return 1
    print("Shire is running, and starts again by itself when your Mac does. "
          "`shire link` prints the link for your phone.")
    return 0


def _stop() -> int:
    path, service = _plist(), f"gui/{os.getuid()}/{LABEL}"
    result = _launchctl("bootout", service)
    if result.returncode != 0 and not path.exists():
        print("Shire wasn't started with `shire start`. If it's running in a terminal, stop it there with Ctrl-C.")
        return 0
    path.unlink(missing_ok=True)
    for _ in range(60):  # it finishes the plugins it's in the middle of first
        if _launchctl("print", service).returncode != 0:
            break
        time.sleep(0.5)
    else:
        print("Shire has been told to stop, and is still finishing what it was doing.", file=sys.stderr)
        return 1
    print("Shire is stopped, and won't start by itself.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="shire", description="An observability platform for always-on laptops and power users.")
    parser.add_argument("--version", action="version", version=f"shire {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run Shire here, until you stop it")
    run.add_argument("--once", action="store_true", help="run every plugin once, show what each found, and stop")
    start = commands.add_parser("start", help="keep Shire running, and start it with your Mac")
    for command in (run, start):
        command.add_argument("--port", type=int, default=PORT, help=f"the port the page is on, {PORT} unless you say")
        command.add_argument("--host", default=EVERYWHERE,
                             help="where it listens: every network unless you say, or 127.0.0.1 for this computer only")
    commands.add_parser("stop", help="stop Shire, and stop it starting by itself")
    commands.add_parser("link", help="print the link to open on your phone")
    args = parser.parse_args(argv)

    os.environ["PATH"] = host.full_path()
    store.ensure_home()
    if args.command == "run":
        return _once() if args.once else _run(args.host, args.port)
    if args.command == "start":
        return _start(args.host, args.port)
    if args.command == "stop":
        return _stop()
    return _link()
