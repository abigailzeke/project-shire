"""This computer: which system it is, and what's running on it.

The built-in checks use this, and so can any plugin script written in
Python, because Shire runs those with its own Python:

    from shire import host
    for process in host.processes(): ...
"""

from __future__ import annotations

import ipaddress
import os
import socket
import subprocess
import sys
import time

from . import fmt

SYSTEM = {"darwin": "macos", "linux": "linux", "win32": "windows"}.get(sys.platform, sys.platform)
SYSTEM_NAME = {"macos": "macOS", "linux": "Linux", "windows": "Windows"}.get(SYSTEM, SYSTEM)


def full_path() -> str:
    """launchd starts programs with a bare PATH, so Homebrew's folders and
    your own go in front of it."""
    home = os.path.expanduser("~")
    front = [f"{home}/.local/bin", "/opt/homebrew/bin", "/usr/local/bin"]
    usual = ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    given = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    rest = [p for p in dict.fromkeys(given + usual) if p not in front]
    return os.pathsep.join(front + rest)


def run(command, timeout: float = 8, cwd=None) -> str:
    """A command's output, or "" if it fails or takes too long."""
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def reach(where: str, port: int = 443, timeout: float = 3):
    """Whether a connection opens, and how many milliseconds it took."""
    try:
        started = time.monotonic()
        with socket.create_connection((where, port), timeout=timeout):
            return True, round((time.monotonic() - started) * 1000)
    except OSError:
        return False, None


TAILSCALE = ipaddress.ip_network("100.64.0.0/10")  # the addresses Tailscale gives out


def addresses() -> list[tuple[str, str]]:
    """Where a phone can find this computer: its Tailscale address, and its
    address on the network it's on, each with a plain name."""
    found, interface = [], ""
    for line in run(["ifconfig"]).splitlines():
        if line and not line[0].isspace():
            interface = line.split(":", 1)[0]
            continue
        parts = line.split()
        if len(parts) < 2 or parts[0] != "inet":
            continue
        try:
            ip = ipaddress.ip_address(parts[1])
        except ValueError:
            continue
        if ip in TAILSCALE:
            found.append(("Tailscale", str(ip)))
        elif ip.is_private and not ip.is_loopback and not ip.is_link_local and interface.startswith(("en", "eth", "wl")):
            found.append(("Your network", str(ip)))
    return sorted(found)


def processes() -> list[dict]:
    """Every running process: pid, parent, CPU, memory in bytes, how long
    it's been running, and its whole command line. The command line is raw,
    so pass it through fmt.tidy_args before showing it."""
    rows = []
    for line in run(["ps", "axww", "-o", "pid=,ppid=,pcpu=,rss=,etime=,args="]).splitlines():
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        try:
            rows.append({
                "pid": int(parts[0]), "ppid": int(parts[1]), "cpu": float(parts[2]),
                "rss": int(parts[3]) * 1024, "uptime": fmt.etime_seconds(parts[4]), "args": parts[5],
            })
        except ValueError:
            continue
    return rows
