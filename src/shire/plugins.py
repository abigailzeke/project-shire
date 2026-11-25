"""Finds every plugin and reads its plugin.yaml.

A plugin is a folder with a plugin.yaml in it. The ones that come with Shire
are in the repo's plugins folder, and yours are in your space. When both have
a folder with the same name, yours is laid on top, setting by setting, so you
can change one line of a built-in plugin without copying it.

The plugins that come with Shire all have names that start with core-, and
that start is kept for them, so a plugin of yours can never clash with one
that Shire adds later.

A plugin's folder can also hold a names.yaml: a plain name for each thing it
finds that has an awkward one.

A plugin that can't be read is still returned, with the problem in plain
words, so it shows on the page instead of quietly going missing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import schemas, store

ID = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")
CORE = "core-"  # how the name of every plugin that comes with Shire starts
_UNIT = {"s": 1, "m": 60, "h": 3600}


def seconds(text, default: int) -> int:
    """30s, 5m or 1h, in seconds."""
    m = re.fullmatch(r"([1-9][0-9]*)(s|m|h)", str(text or ""))
    return int(m[1]) * _UNIT[m[2]] if m else default


@dataclass(frozen=True)
class Plugin:
    id: str                    # its folder's name
    config: dict               # its plugin.yaml, with yours on top
    folders: tuple             # where its files are: yours first, then the built-in one
    problem: str | None = None  # why it can't run, in plain words
    core: bool = False         # whether it comes with Shire
    names: dict = field(default_factory=dict)  # its names.yaml: a plain name for a key or name

    @property
    def name(self) -> str:
        name = self.config.get("name")
        return name if isinstance(name, str) and name else self.id

    @property
    def check(self) -> str | None:
        return self.config.get("check")

    @property
    def every(self) -> int:
        return seconds(self.config.get("every"), 60)

    @property
    def timeout(self) -> int:
        return seconds(self.config.get("timeout"), 10)

    @property
    def enabled(self) -> bool:
        return self.config.get("enabled") is not False


def builtin_dir() -> Path:
    """The plugins that come with Shire: inside the package when it's
    installed, and at the top of the repo when it runs from a clone."""
    packaged = Path(__file__).parent / "builtin_plugins"
    return packaged if packaged.is_dir() else Path(__file__).resolve().parents[2] / "plugins"


def _merge(under: dict, over: dict) -> dict:
    """over on top of under. options is merged one level down, so you can
    change one option and keep the rest."""
    out = {**under, **over}
    if isinstance(under.get("options"), dict) and isinstance(over.get("options"), dict):
        out["options"] = {**under["options"], **over["options"]}
    return out


def load(plugin_id: str, folders: list[Path], core: bool = False) -> Plugin:
    """One plugin from its folders, the built-in one first."""
    config: dict = {}
    problem = None
    if not ID.fullmatch(plugin_id):
        problem = "A plugin's folder name can only have small letters, numbers and dashes."
    elif plugin_id.startswith(CORE) and not core:
        problem = (f"Shire has no plugin called {plugin_id}. "
                   f"Names that start with {CORE} are kept for the plugins that come with it.")
    try:
        for folder in folders:
            config = _merge(config, store.read_yaml(folder / "plugin.yaml"))
    except ValueError as e:
        problem = problem or str(e)
    if not problem:
        found = schemas.problems("plugin", config)
        if found:
            problem = f"plugin.yaml: {found[0]}"
    names: dict = {}
    for folder in folders:
        if (folder / "names.yaml").is_file():
            try:
                listed = store.read_yaml(folder / "names.yaml")
            except ValueError as e:
                problem = problem or str(e)
            else:
                names.update({pattern: plain for pattern, plain in listed.items() if isinstance(plain, str) and plain})
    return Plugin(plugin_id, config, tuple(reversed(folders)), problem, core, names)


def find() -> dict[str, Plugin]:
    """Every plugin, by its folder's name."""
    folders: dict[str, list[Path]] = {}
    core: set[str] = set()
    for base, built_in in ((builtin_dir(), True), (store.plugins_home(), False)):
        if not base.is_dir():
            continue
        for folder in sorted(base.iterdir()):
            if folder.is_dir() and not folder.name.startswith(".") and (folder / "plugin.yaml").is_file():
                folders.setdefault(folder.name, []).append(folder)
                if built_in:
                    core.add(folder.name)
    return {plugin_id: load(plugin_id, found, plugin_id in core) for plugin_id, found in sorted(folders.items())}
