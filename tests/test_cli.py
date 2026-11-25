"""The shire command: link, start and stop."""

import os
import plistlib
from types import SimpleNamespace

from shire import cli, host, store

IFCONFIG = """\
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet6 fe80::1c2b%en0 prefixlen 64 secured scopeid 0xb
\tinet 192.168.1.23 netmask 0xffffff00 broadcast 192.168.1.255
utun4: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1280
\tinet 100.64.0.9 --> 100.64.0.9 netmask 0xffffffff
bridge100: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.64.1 netmask 0xffffff00 broadcast 192.168.64.255
"""


def test_addresses_names_tailscale_and_your_network(monkeypatch):
    monkeypatch.setattr(host, "run", lambda *a, **k: IFCONFIG)
    assert host.addresses() == [("Tailscale", "100.64.0.9"), ("Your network", "192.168.1.23")]


def test_link_prints_links_with_your_key(space, monkeypatch, capsys):
    monkeypatch.setattr(host, "addresses", lambda: [("Tailscale", "100.64.0.1")])
    assert cli.main(["link"]) == 0
    out = capsys.readouterr().out
    assert "Shire isn't running" in out
    assert f"http://100.64.0.1:5190/?key={store.key()}" in out
    assert f"http://localhost:5190/?key={store.key()}" in out


def test_link_uses_the_port_a_running_shire_wrote_down(space, monkeypatch, capsys):
    monkeypatch.setattr(host, "addresses", lambda: [("Tailscale", "100.64.0.1")])
    store.write_json(store.server_path(), {"pid": os.getpid(), "port": 6000, "host": "0.0.0.0"})
    cli.main(["link"])
    out = capsys.readouterr().out
    assert "Open one of these on your phone" in out
    assert f"http://100.64.0.1:6000/?key={store.key()}" in out


def test_link_forgets_a_shire_that_has_gone(space, monkeypatch, capsys):
    monkeypatch.setattr(host, "addresses", lambda: [])
    store.write_json(store.server_path(), {"pid": 2 ** 22 + 12345, "port": 6000, "host": "0.0.0.0"})
    cli.main(["link"])
    out = capsys.readouterr().out
    assert "Shire isn't running" in out and ":5190/" in out


def test_start_hands_shire_to_launchd_and_stop_takes_it_back(space, monkeypatch, tmp_path, capsys):
    plist, calls = tmp_path / "agents" / "shire.plist", []
    monkeypatch.setattr(cli, "_plist", lambda: plist)
    def launchctl(*args):  # once it's told to stop, launchd no longer knows it
        calls.append(args[0])
        return SimpleNamespace(returncode=113 if args[0] == "print" else 0, stdout="", stderr="")

    monkeypatch.setattr(cli, "_launchctl", launchctl)
    monkeypatch.setattr(cli, "_running", lambda: {"port": 6000})
    monkeypatch.setattr(host, "SYSTEM", "macos")

    assert cli.main(["start", "--port", "6000"]) == 0
    job = plistlib.loads(plist.read_bytes())
    assert job["ProgramArguments"][1:] == ["-m", "shire", "run", "--port", "6000", "--host", "0.0.0.0"]
    assert job["RunAtLoad"] is True and job["KeepAlive"] is True
    assert job["EnvironmentVariables"]["SHIRE_HOME"] == str(space.home)
    assert "Shire is running" in capsys.readouterr().out

    assert cli.main(["stop"]) == 0
    assert not plist.exists()
    assert calls == ["bootout", "bootstrap", "bootout", "print"]
    assert "Shire is stopped" in capsys.readouterr().out


def test_stop_when_it_was_never_started(space, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "_plist", lambda: tmp_path / "agents" / "shire.plist")
    monkeypatch.setattr(cli, "_launchctl", lambda *a: SimpleNamespace(returncode=3, stdout="", stderr="No such process"))
    assert cli.main(["stop"]) == 0
    assert "wasn't started with `shire start`" in capsys.readouterr().out


def test_run_says_plainly_when_the_port_is_taken(space, monkeypatch, capsys):
    import socket
    monkeypatch.setattr(cli, "BIND_TRIES", 1)
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        assert cli.main(["run", "--host", "127.0.0.1", "--port", str(taken.getsockname()[1])]) == 1
    assert "can't use port" in capsys.readouterr().err
    assert not store.server_path().exists()
