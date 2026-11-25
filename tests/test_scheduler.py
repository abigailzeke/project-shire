"""The scheduler: schedules, time limits, the standard format and what's saved."""

import json
import time

from shire import schemas, store
from shire.scheduler import Scheduler

QUICK = ("import json\nprint(json.dumps({'items': [{'key': 'cpu', 'name': 'Processor', 'value': 12, 'unit': '%'},"
         " {'key': 'net', 'name': 'Network', 'value': 'online', 'state': 'good'}]}))\n")


def output(space, plugin_id):
    return json.loads((space.home / "data" / plugin_id / "output.json").read_text())


def wait(futures):
    for future in futures:
        future.result(timeout=20)


def test_once_saves_each_plugins_output_in_the_standard_format(space):
    space.add("quick", "name: Quick\ncheck: script\nscript: collect.py\n", collect_py=QUICK)
    before = int(time.time())
    Scheduler().once()
    out = output(space, "quick")
    assert schemas.problems("output", out) == []
    assert out["plugin"] == "quick" and out["ok"] is True and out["taken"] >= before
    assert out["items"][0]["value"] == 12


def test_a_plugin_that_hangs_doesnt_stop_the_others(space):
    space.add("quick", "name: Quick\ncheck: script\nscript: collect.py\n", collect_py=QUICK)
    space.add("slow", "name: Slow\ncheck: script\nscript: collect.py\ntimeout: 1s\n",
              collect_py="import time\ntime.sleep(60)\n")
    space.add("broken", "name: Broken\ncheck: website\n")
    started = time.monotonic()
    outputs = Scheduler().once()
    assert time.monotonic() - started < 8
    assert outputs["quick"]["ok"] is True
    assert "longer than 1 s" in outputs["slow"]["error"]
    assert outputs["broken"]["error"] == "plugin.yaml: url is missing"
    assert output(space, "broken")["ok"] is False  # the problem is saved, so the page can show it


def test_output_that_isnt_in_the_standard_format_is_refused(space):
    space.add("bad", "name: Bad\ncheck: script\nscript: collect.py\n",
              collect_py="print('{\"items\": [{\"name\": \"no key\"}]}')\n")
    out = Scheduler().once()["bad"]
    assert out["ok"] is False and out["items"] == []
    assert out["error"] == "Its output isn't in the standard format: items[0].key is missing."


def test_two_items_cant_share_a_key(space):
    space.add("twice", "name: Twice\ncheck: script\nscript: collect.py\n",
              collect_py="print('{\"items\": [{\"key\": \"a\", \"name\": \"A\"}, {\"key\": \"a\", \"name\": \"B\"}]}')\n")
    assert "two items share the key 'a'" in Scheduler().once()["twice"]["error"]


def test_each_plugin_keeps_its_own_schedule(space):
    space.add("fast", "name: Fast\ncheck: script\nscript: collect.py\nevery: 30s\n", collect_py=QUICK)
    space.add("slow", "name: Slow\ncheck: script\nscript: collect.py\nevery: 15m\n", collect_py=QUICK)
    s = Scheduler()
    first = s.tick(now=1000)
    assert len(first) == 2  # everything runs when Shire starts
    wait(first)
    assert s.tick(now=1010) == []
    again = s.tick(now=1031)
    assert len(again) == 1 and set(s.running) == {"fast"}
    wait(again)
    wait(s.tick(now=1000 + 15 * 60))
    assert output(space, "slow")["ok"] is True


def test_a_changed_plugin_yaml_runs_at_once(space):
    space.add("p", "name: P\ncheck: script\nscript: collect.py\nevery: 1h\n", collect_py=QUICK)
    s = Scheduler()
    wait(s.tick(now=1000))
    assert s.tick(now=1005) == []
    space.add("p", "name: Renamed\ncheck: script\nscript: collect.py\nevery: 1h\n")
    assert len(s.tick(now=1010)) == 1


def test_a_new_folder_is_picked_up_without_a_restart(space):
    s = Scheduler()
    assert s.tick(now=1000) == []
    space.add("new", "name: New\ncheck: script\nscript: collect.py\n", collect_py=QUICK)
    wait(s.tick(now=1005))
    assert output(space, "new")["ok"] is True


def test_off_means_it_doesnt_run_and_your_switch_decides(space):
    space.add("off", "name: Off\ncheck: script\nscript: collect.py\nenabled: false\n", collect_py=QUICK)
    space.add("on", "name: On\ncheck: script\nscript: collect.py\n", collect_py=QUICK)
    store.write_json(store.settings_path("on"), {"enabled": False})
    s = Scheduler()
    assert s.once() == {}
    store.write_json(store.settings_path("off"), {"enabled": True})
    assert set(s.once()) == {"off"}


def test_history_keeps_the_numbers_it_was_asked_for(space):
    space.add("p", "name: P\ncheck: script\nscript: collect.py\nhistory: [cpu, net]\n", collect_py=QUICK)
    Scheduler().once()
    (point,) = json.loads((space.home / "data" / "p" / "history.json").read_text())
    assert point["cpu"] == 12 and "t" in point
    assert point["net"] == 1  # no number, so it keeps whether it was good
    Scheduler().once()  # less than a minute later, so no second point
    assert len(json.loads((space.home / "data" / "p" / "history.json").read_text())) == 1


def test_nothing_is_ever_written_into_your_plugins_folder(space):
    folder = space.add("p", "name: P\ncheck: script\nscript: collect.py\nhistory: [cpu]\n", collect_py=QUICK)
    Scheduler().once()
    assert sorted(f.name for f in folder.iterdir()) == ["collect.py", "plugin.yaml"]
    assert sorted(f.name for f in (space.home / "data" / "p").iterdir()) == ["history.json", "output.json"]


def test_names_yaml_gives_plain_names_and_keeps_the_original(space):
    space.add("p", "name: P\ncheck: script\nscript: collect.py\n", collect_py=(
        "import json\nprint(json.dumps({'items': [{'key': 'com.x.updater.agent', 'name': 'Updater agent'},"
        " {'key': 'program:xd', 'name': 'xd'}, {'key': 'plain', 'name': 'Already plain'}]}))\n"))
    (space.home / "plugins" / "p" / "names.yaml").write_text('"com.x.*": X updater\n"xd": X helper\n')
    Scheduler().once()
    items = {i["key"]: i for i in output(space, "p")["items"]}
    assert (items["com.x.updater.agent"]["name"], items["com.x.updater.agent"]["original"]) == ("X updater", "Updater agent")
    assert (items["program:xd"]["name"], items["program:xd"]["original"]) == ("X helper", "xd")
    assert items["plain"] == {"key": "plain", "name": "Already plain"}
