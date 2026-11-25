"""Your space: the one folder that holds everything of yours.

Nothing of yours ever goes in the repo. It lives in ~/.config/project-shire,
or wherever SHIRE_HOME points, in three folders, one for each writer, so
nothing can overwrite anything else:

    plugins/        you write: your plugins, and your changes to built-in ones
    user-settings/  the page writes: your names, choices and groups
    data/           the scheduler writes: what each plugin found. Safe to delete.

A plugin has a folder of the same name in each of the three.

This is also the only place that reads and writes those files, so every
write is done the same safe way."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from pathlib import Path

import yaml


def home() -> Path:
    return Path(os.environ.get("SHIRE_HOME") or "~/.config/project-shire").expanduser()


def plugins_home() -> Path:
    """What you write: a folder for each plugin of yours."""
    return home() / "plugins"


def settings_path(plugin_id: str) -> Path:
    """What the page writes for one plugin: your names and choices."""
    return home() / "user-settings" / plugin_id / "settings.json"


def groups_path() -> Path:
    """What the page writes for the whole page: your groups."""
    return home() / "user-settings" / "groups.json"


def data_dir(plugin_id: str) -> Path:
    """What the scheduler writes for one plugin: its output and its history."""
    return home() / "data" / plugin_id


def server_path() -> Path:
    """Where a running Shire writes down its port, so `shire link` knows it."""
    return home() / "data" / "server.json"


def key_path() -> Path:
    return home() / "key"


def key() -> str:
    """The page's key: a long random word that only you can read. It's made
    the first time it's needed. After that it's only ever read, so to change
    your key, change the file."""
    path = key_path()
    try:
        found = path.read_text(encoding="utf-8").strip()
    except OSError:
        found = ""
    if found:
        return found
    ensure_home()
    made = secrets.token_urlsafe(24)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(made + "\n")
    return made


def ensure_home() -> Path:
    """Makes your space if it isn't there, readable only by you."""
    path = home()
    if not path.is_dir():
        path.mkdir(parents=True, mode=0o700)
    return path


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, value) -> None:
    """Written to a temporary file and then swapped in, so a reader never
    sees half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_yaml(path) -> dict:
    """A YAML file's settings. If it can't be read, the ValueError says why
    in words that can go straight onto the page."""
    name = Path(path).name
    try:
        with open(path, encoding="utf-8") as f:
            value = yaml.safe_load(f)
    except OSError as e:
        raise ValueError(f"{name} can't be opened: {e.strerror}") from e
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark else ""
        raise ValueError(f"{name} isn't valid YAML{where}") from e
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} should be settings like `name: Wallet`, one on each line")
    for key in value:
        # YAML reads a bare on, off, yes or no as true or false, even as a name.
        if not isinstance(key, str):
            raise ValueError(f"{name}: {key!r} can't be the name of a setting")
    return value
