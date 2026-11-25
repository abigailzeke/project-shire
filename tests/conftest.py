"""An empty space of yours and an empty folder of built-in plugins for every
test, so nothing here touches the real ones."""

import stat
import textwrap
from types import SimpleNamespace

import pytest

from shire import plugins


@pytest.fixture
def space(tmp_path, monkeypatch):
    home, builtin = tmp_path / "space", tmp_path / "builtin"
    home.mkdir()
    builtin.mkdir()
    monkeypatch.setenv("SHIRE_HOME", str(home))
    monkeypatch.setattr(plugins, "builtin_dir", lambda: builtin)

    def add(plugin_id, yaml_text, builtin_too=False, **files):
        """Writes a plugin: its plugin.yaml, and any other files by name."""
        folder = (builtin if builtin_too else home / "plugins") / plugin_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "plugin.yaml").write_text(textwrap.dedent(yaml_text))
        for name, text in files.items():
            name = name.replace("_", ".", 1)
            (folder / name).write_text(textwrap.dedent(text))
            if not name.endswith(".py"):
                (folder / name).chmod((folder / name).stat().st_mode | stat.S_IXUSR)
        return folder

    return SimpleNamespace(home=home, builtin=builtin, add=add)
