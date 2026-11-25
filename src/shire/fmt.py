"""Plain words for numbers, and command lines that are safe to show."""

from __future__ import annotations

import os
import re
import time


def dur(seconds) -> str:
    """How long, in the two largest units: 45 s, 12 min, 3 h 5 min, 2 d 4 h."""
    s = int(seconds)
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min"
    if s < 86400:
        h, m = divmod(s // 60, 60)
        return f"{h} h {m} min" if m else f"{h} h"
    d, h = divmod(s // 3600, 24)
    return f"{d} d {h} h" if h else f"{d} d"


def size(count) -> str:
    """Bytes as B, KB, MB or GB."""
    n = float(count)
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def when(timestamp) -> str:
    """A moment as 24 Nov 18:51, in this computer's time."""
    t = time.localtime(timestamp)
    return f"{t.tm_mday} {time.strftime('%b', t)} {t.tm_hour:02d}:{t.tm_min:02d}"


def etime_seconds(text: str) -> int:
    """ps's elapsed time, [[dd-]hh:]mm:ss, in seconds."""
    days = 0
    if "-" in text:
        d, text = text.split("-", 1)
        days = int(d)
    parts = [int(p) for p in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return days * 86400 + h * 3600 + m * 60 + s


_SECRET = re.compile(r"(?i)((?:--?|\b)(?:token|key|secret|password|passwd|pass|auth|apikey|api-key)[=:\s]+)\S+")
_LONG_BLOB = re.compile(r"[A-Za-z0-9+/_\-]{40,}")
_UUID = re.compile(r"\b([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


def tidy_args(args: str, limit: int = 180) -> str:
    """A command line that's safe to show: secrets masked, long tokens cut,
    and the home folder as ~."""
    args = _SECRET.sub(r"\1•••", args)
    args = _LONG_BLOB.sub("…", args)
    args = _UUID.sub(r"\1…", args)
    args = args.replace(os.path.expanduser("~"), "~")
    return args if len(args) <= limit else args[: limit - 1] + "…"
