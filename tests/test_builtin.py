"""The plugins that come with Shire: every plugin.yaml is sound, and on a
Mac every one of them really runs and keeps to the standard format."""

import os
import sys

import pytest

from shire import plugins, schemas, scheduler


# Asks Claude Code to check every connector live, so it only runs when asked:
#   SHIRE_SLOW_TESTS=1 .venv/bin/pytest
SLOW = {"core-connectors"}


@pytest.fixture
def builtin(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIRE_HOME", str(tmp_path))  # the real plugins, in an empty space
    return plugins.find()


def test_there_are_built_in_plugins(builtin):
    assert set(builtin) == {"core-apps", "core-claude-code", "core-connectors", "core-docker", "core-jobs",
                            "core-obsidian", "core-os-metrics", "core-scripts"}


def test_every_built_in_plugin_is_named_core(builtin):
    assert all(pid.startswith("core-") and p.core for pid, p in builtin.items())


def test_every_built_in_plugin_yaml_is_sound(builtin):
    assert {pid: p.problem for pid, p in builtin.items() if p.problem} == {}


@pytest.mark.skipif(sys.platform != "darwin", reason="the built-in scripts are for macOS")
def test_every_built_in_plugin_runs_and_keeps_to_the_standard_format(builtin):
    for plugin in builtin.values():
        if plugin.id in SLOW and not os.environ.get("SHIRE_SLOW_TESTS"):
            continue
        out = scheduler.run(plugin)
        assert "error" not in out, f"{plugin.id}: {out.get('error')}"
        assert schemas.problems("output", out) == []


def test_os_metrics_reads_every_part_of_the_mac(builtin):
    if sys.platform != "darwin":
        pytest.skip("the built-in scripts are for macOS")
    out = scheduler.run(builtin["core-os-metrics"])
    keys = [item["key"] for item in out["items"]]
    assert keys[:8] == ["awake", "power", "temperature", "memory", "processor", "storage", "network", "this-mac"]
    assert not [i["key"] for i in out["items"] if str(i.get("note", "")).startswith("It couldn't be read")]


def test_obsidian_asks_for_a_vault_until_you_name_one(builtin):
    out = scheduler.run(builtin["core-obsidian"])
    assert out["ok"] is False and "Name a folder" in out["reason"]


def test_a_claude_session_keeps_its_key_when_it_restarts(builtin):
    import importlib.util
    spec = importlib.util.spec_from_file_location("collect", builtin["core-claude-code"].folders[-1] / "collect.py")
    collect = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collect)
    tonight = [{"args": "claude", "uptime": 50}, {"args": "claude --remote-control Robin", "uptime": 900},
               {"args": "claude -p --output-format stream-json", "uptime": 30}, {"args": "claude", "uptime": 700}]
    assert collect.session_keys(tonight) == ["session:terminal:2", "session:remote-control", "session:app", "session:terminal"]
    tomorrow = [{"args": "claude --resume abc --remote-control Sam", "uptime": 5}]  # new process, new name
    assert collect.session_keys(tomorrow) == ["session:remote-control"]
