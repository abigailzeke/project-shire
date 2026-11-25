"""For plugin scripts written in Python.

Shire hands a script its options as JSON on standard input, and the script
prints what it found in the standard format. These three do both ends:

    from shire import script

    options = script.options()
    script.done([{"key": "a", "name": "A", "value": 1}], summary="One thing")

or, when what it watches isn't there:

    script.nothing("Docker isn't installed.")
"""

from __future__ import annotations

import json
import sys


def options() -> dict:
    """The `options:` from the plugin's plugin.yaml. Empty when the script is
    run by hand in a terminal."""
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return {}
    found = event.get("options") if isinstance(event, dict) else None
    return found if isinstance(found, dict) else {}


def done(items: list, summary: str | None = None) -> None:
    """Prints what the script found."""
    out: dict = {"items": items}
    if summary:
        out["summary"] = summary
    print(json.dumps(out))


def nothing(reason: str) -> None:
    """Says there's nothing to read, and why. It isn't a fault."""
    print(json.dumps({"ok": False, "reason": reason, "items": []}))
