"""Each kind of check, against the real thing: a real server, a real port,
a real process, real files and real scripts."""

import http.server
import json
import socket
import socketserver
import subprocess
import sys
import threading
import time

import pytest

from shire import checks, plugins


def only(space, plugin_id="p"):
    return plugins.find()[plugin_id]


@pytest.fixture
def server():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(404 if self.path == "/missing" else 500 if self.path == "/broken" else 200)
            self.end_headers()

        def log_message(self, *args):
            pass

    class Server(http.server.ThreadingHTTPServer):
        def server_bind(self):  # skips HTTPServer's look-up of this computer's name, which can take seconds
            socketserver.TCPServer.server_bind(self)

    httpd = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def closed_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------ website

def test_website_up(space, server):
    space.add("p", f"name: Wallet\ncheck: website\nurl: http://127.0.0.1:{server}/\n")
    (item,) = checks.run(only(space))["items"]
    assert item["state"] == "good" and item["unit"] == "ms" and isinstance(item["value"], int)
    assert item["name"] == "Wallet" and item["facts"]["Answer"] == 200


def test_website_answering_with_an_error(space, server):
    space.add("p", f"name: W\ncheck: website\nurl: http://127.0.0.1:{server}/missing\n")
    assert checks.run(only(space))["items"][0]["state"] == "warn"
    space.add("p", f"name: W\ncheck: website\nurl: http://127.0.0.1:{server}/broken\n")
    assert checks.run(only(space))["items"][0]["state"] == "bad"


def test_website_down(space):
    space.add("p", f"name: W\ncheck: website\nurl: http://127.0.0.1:{closed_port()}/\n")
    (item,) = checks.run(only(space))["items"]
    assert (item["value"], item["state"]) == ("down", "bad")


# --------------------------------------------------------------------- port

def test_port(space, server):
    space.add("p", f"name: P\ncheck: port\nport: {server}\n")
    assert checks.run(only(space))["items"][0]["value"] == "listening"
    space.add("p", f"name: P\ncheck: port\nport: {closed_port()}\n")
    (item,) = checks.run(only(space))["items"]
    assert (item["value"], item["state"]) == ("closed", "bad")


# ------------------------------------------------------------------ program

def test_program(space):
    marker = f"shire-test-{time.time_ns()}"
    space.add("p", f"name: Tracker\ncheck: program\nmatch: {marker}\n")
    assert checks.run(only(space))["items"][0]["value"] == "not running"
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", marker])
    try:
        time.sleep(0.3)
        (item,) = checks.run(only(space))["items"]
        assert (item["value"], item["state"]) == ("running", "good")
        assert item["facts"]["Processes"] == 1
    finally:
        child.kill()
        child.wait()


def test_program_with_a_bad_pattern(space):
    space.add("p", "name: T\ncheck: program\nmatch: '('\n")
    assert "isn't a pattern" in checks.run(only(space))["error"]


# --------------------------------------------------------------------- file

def test_file_not_named_and_not_there(space, tmp_path):
    space.add("p", "name: F\ncheck: file\npath: null\n")
    out = checks.run(only(space))
    assert out["ok"] is False and "Name a file" in out["reason"] and "error" not in out
    space.add("p", f"name: F\ncheck: file\npath: {tmp_path}/nope.json\n")
    assert "There's no file" in checks.run(only(space))["reason"]


def test_file_json_object_becomes_items(space, tmp_path):
    (tmp_path / "f.json").write_text(json.dumps({"week": 2, "plan": "Pro", "live": True, "more": [1, 2]}))
    space.add("p", f"name: F\ncheck: file\npath: {tmp_path}/f.json\n")
    items = {i["key"]: i for i in checks.run(only(space))["items"]}
    assert items["week"]["value"] == 2 and items["plan"]["value"] == "Pro" and items["live"]["value"] == "yes"
    assert items["more"]["value"] is None and items["more"]["note"] == "[1, 2]"


def test_file_already_in_the_standard_format_is_shown_as_it_is(space, tmp_path):
    (tmp_path / "f.json").write_text(json.dumps({"summary": "s", "items": [{"key": "a", "name": "A", "value": 1}]}))
    space.add("p", f"name: F\ncheck: file\npath: {tmp_path}/f.json\n")
    assert checks.run(only(space)) == {"summary": "s", "items": [{"key": "a", "name": "A", "value": 1}]}


def test_file_text(space, tmp_path):
    (tmp_path / "note.md").write_text("# Hello\n\nworld\n")
    space.add("p", f"name: F\ncheck: file\npath: {tmp_path}/note.md\n")
    (item,) = checks.run(only(space))["items"]
    assert item["note"] == "# Hello\n\nworld" and "Changed" in item["facts"]


# ------------------------------------------------------------------- folder

def test_folder(space, tmp_path):
    vault = tmp_path / "vault"
    (vault / "sub").mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    for name in ("a.md", "sub/b.md", "c.txt", ".hidden.md", ".obsidian/d.md"):
        (vault / name).write_text("x")
    space.add("p", f"name: Vault\ncheck: folder\npath: {vault}\npattern: '*.md'\n")
    out = checks.run(only(space))
    assert out["items"][0] == {"key": "files", "name": "Files", "value": 2}
    recent = {i["key"]: i for i in out["items"][1:]}
    assert set(recent) == {"file:a.md", "file:sub/b.md"}
    assert recent["file:sub/b.md"]["name"] == "b" and recent["file:sub/b.md"]["facts"] == {"Folder": "sub"}


def test_folder_not_named(space):
    space.add("p", "name: Vault\ncheck: folder\npath: null\n")
    assert "Name a folder" in checks.run(only(space))["reason"]


# ------------------------------------------------------------------- script

def test_script_is_handed_its_options_and_prints_items(space):
    space.add("p", "name: Greeter\ncheck: script\nscript: collect.py\noptions: {say: hello}\n", collect_py="""
        import json, sys
        event = json.load(sys.stdin)
        print(json.dumps({"items": [{"key": "g", "name": event["name"], "value": event["options"]["say"]}]}))
    """)
    assert checks.run(only(space)) == {"items": [{"key": "g", "name": "Greeter", "value": "hello"}]}


def test_script_in_any_language(space):
    space.add("p", "name: Shell\ncheck: script\nscript: collect.sh\n", collect_sh="""\
        #!/bin/sh
        echo '{"items": [{"key": "a", "name": "A"}]}'
    """)
    assert checks.run(only(space)) == {"items": [{"key": "a", "name": "A"}]}


def test_script_that_hangs_is_stopped(space):
    space.add("p", "name: Slow\ncheck: script\nscript: collect.py\ntimeout: 1s\n",
              collect_py="import time\ntime.sleep(60)\n")
    started = time.monotonic()
    out = checks.run(only(space))
    assert time.monotonic() - started < 5
    assert out["ok"] is False and "longer than 1 s" in out["error"]


def test_script_that_crashes_says_why(space):
    space.add("p", "name: C\ncheck: script\nscript: collect.py\n", collect_py="raise RuntimeError('no battery')\n")
    assert "RuntimeError: no battery" in checks.run(only(space))["error"]


def test_script_that_prints_nonsense(space):
    space.add("p", "name: N\ncheck: script\nscript: collect.py\n", collect_py="print('hello')\n")
    assert "didn't print JSON" in checks.run(only(space))["error"]


def test_script_that_isnt_there(space):
    space.add("p", "name: N\ncheck: script\nscript: gone.py\n")
    assert "isn't in the plugin's folder" in checks.run(only(space))["error"]


def test_script_for_another_system_only(space):
    space.add("p", "name: N\ncheck: script\nscript: {windows: win.ps1}\n")
    out = checks.run(only(space))
    assert out["ok"] is False and "doesn't work on" in out["reason"]


def test_your_script_wins_over_the_built_in_one(space):
    space.add("p", "name: P\ncheck: script\nscript: collect.py\n", builtin_too=True,
              collect_py="print('{\"items\": [{\"key\": \"k\", \"name\": \"built in\"}]}')\n")
    space.add("p", "every: 5m\n", collect_py="print('{\"items\": [{\"key\": \"k\", \"name\": \"yours\"}]}')\n")
    assert checks.run(only(space))["items"][0]["name"] == "yours"
