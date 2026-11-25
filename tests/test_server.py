"""The server: your key, and the four things the page can ask."""

import pytest

from shire import plugins, scheduler, schemas, server, store

WALLET = "name: Wallet\ncheck: port\nport: 1\n"


@pytest.fixture
def stranger(space, tmp_path, monkeypatch):
    """A browser that has never opened the link."""
    monkeypatch.setattr(server, "page_dir", lambda: tmp_path / "no-page")
    return server.create_app().test_client()


@pytest.fixture
def page(stranger):
    """A browser that has."""
    stranger.set_cookie(server.COOKIE, store.key())
    return stranger


def run_once():
    s = scheduler.Scheduler()
    s.once()
    s.close()


# ------------------------------------------------------------------ the key
def test_the_key_is_made_once_and_only_you_can_read_it(space):
    key = store.key()
    assert len(key) >= 24
    assert store.key() == key
    assert store.key_path().stat().st_mode & 0o077 == 0


def test_your_own_key_is_kept(space):
    store.key_path().write_text("a key of my own\n")
    assert store.key() == "a key of my own"


def test_without_the_key_everything_is_locked(stranger):
    r = stranger.get("/")
    assert r.status_code == 401 and b"This page is locked" in r.data
    r = stranger.get("/api/status")
    assert r.status_code == 401 and r.get_json() == {"error": "This needs your key."}
    assert stranger.put("/api/groups", json=[]).status_code == 401
    assert not store.groups_path().exists()


def test_the_link_lets_a_phone_in_and_takes_the_key_out_of_the_address(stranger):
    r = stranger.get(f"/?key={store.key()}")
    assert r.status_code == 303 and r.headers["Location"] == "/"
    assert "HttpOnly" in r.headers["Set-Cookie"] and "SameSite=Lax" in r.headers["Set-Cookie"]
    assert stranger.get("/api/status").status_code == 200


def test_a_wrong_key_stays_locked(stranger):
    r = stranger.get("/?key=a-guess")
    assert r.status_code == 401 and b"That isn't the key" in r.data
    assert "Set-Cookie" not in r.headers
    assert stranger.get("/api/status").status_code == 401


def test_a_key_in_an_api_address_isnt_taken(stranger):
    assert stranger.get(f"/api/status?key={store.key()}").status_code == 401


# ------------------------------------------------------------------- status
def test_status_has_every_plugin_with_what_it_found_and_your_choices(page, space):
    space.add("wallet", WALLET + "description: My money\ndisplay: number\nhistory: [port]\n")
    space.add("asleep", WALLET + "enabled: false\n")
    run_once()
    store.write_json(store.settings_path("wallet"), {"name": "My money", "items": {"port": {"watch": True}}})

    body = page.get("/api/status").get_json()
    assert schemas.problems("status", body) == []
    assert body["shire"]["system"] in ("macOS", "Linux", "Windows")
    assert [g["id"] for g in body["groups"]] == ["computer", "agent", "docker"]
    asleep, wallet = body["plugins"]
    assert (wallet["id"], wallet["name"], wallet["core"], wallet["enabled"]) == ("wallet", "Wallet", False, True)
    assert (wallet["description"], wallet["display"], wallet["every"], wallet["history"]) == ("My money", "number", 60, ["port"])
    assert wallet["output"]["plugin"] == "wallet"
    assert wallet["settings"] == {"name": "My money", "items": {"port": {"watch": True}}}
    assert (asleep["enabled"], asleep["output"], asleep["settings"]) == (False, None, {})


def test_a_plugin_that_cant_run_says_why(page, space):
    space.add("wallet", "name: Wallet\ncheck: website\n")
    (wallet,) = page.get("/api/status").get_json()["plugins"]
    assert wallet["problem"] == "plugin.yaml: url is missing"


def test_a_settings_file_someone_broke_reads_as_no_choices(page, space):
    space.add("wallet", WALLET)
    store.write_json(store.settings_path("wallet"), {"items": "nonsense"})
    body = page.get("/api/status").get_json()
    assert body["plugins"][0]["settings"] == {}
    assert schemas.problems("status", body) == []


# ------------------------------------------------------------- your choices
def test_saving_your_choices_for_a_plugin(page, space):
    space.add("wallet", WALLET)
    settings = {"enabled": False, "name": "My money",
             "items": {"a": {"name": "A", "note": "A line of mine", "hidden": True, "items": {"b": {"watch": True}}}}}
    r = page.put("/api/settings/wallet", json=settings)
    assert r.status_code == 200 and r.get_json() == settings
    assert store.read_json(store.settings_path("wallet")) == settings
    assert scheduler.enabled(plugins.find()["wallet"]) is False  # the scheduler reads the same file


def test_saving_only_ever_writes_into_user_settings(page, space):
    space.add("wallet", WALLET)
    page.put("/api/settings/wallet", json={"name": "Mine"})
    page.put("/api/groups", json=[])
    written = sorted(str(p.relative_to(space.home)) for p in space.home.rglob("*") if p.is_file())
    assert written == ["key", "plugins/wallet/plugin.yaml", "user-settings/groups.json", "user-settings/wallet/settings.json"]


def test_a_choice_shire_doesnt_know_is_refused_in_plain_words(page, space):
    space.add("wallet", WALLET)
    r = page.put("/api/settings/wallet", json={"items": {"a": {"nme": "A"}}})
    assert r.status_code == 400 and r.get_json() == {"error": "items.a.nme isn't something Shire knows"}
    assert not store.settings_path("wallet").exists()


def test_choices_for_a_plugin_that_isnt_there_are_refused(page, space):
    r = page.put("/api/settings/nothing", json={})
    assert r.status_code == 404 and r.get_json() == {"error": "Shire has no plugin called nothing."}
    assert page.put("/api/settings/..%2F..%2Fkey", json={}).status_code in (404, 405)  # no such address at all
    assert not (space.home / "user-settings").exists()


def test_saving_your_groups(page):
    groups = [{"id": "home", "name": "Home", "note": "Everything I care about", "colour": "lilac", "plugins": ["wallet"]}]
    assert page.put("/api/groups", json=groups).status_code == 200
    assert page.get("/api/status").get_json()["groups"] == groups
    r = page.put("/api/groups", json=[{"id": "home", "name": "Home"}])
    assert r.status_code == 400 and r.get_json() == {"error": "[0].plugins is missing"}
    assert page.get("/api/status").get_json()["groups"] == groups


def test_no_groups_at_all_is_a_choice_too(page):
    page.put("/api/groups", json=[])
    assert page.get("/api/status").get_json()["groups"] == []


def test_another_site_cant_save_anything(page, space):
    space.add("wallet", WALLET)
    r = page.put("/api/settings/wallet", json={}, headers={"Origin": "https://elsewhere.example"})
    assert r.status_code == 403
    r = page.put("/api/settings/wallet", data="{}", content_type="text/plain")
    assert r.status_code == 415
    r = page.put("/api/settings/wallet", data="{not json", content_type="application/json")
    assert r.status_code == 400
    assert not store.settings_path("wallet").exists()
    assert page.put("/api/settings/wallet", json={}, headers={"Origin": "http://localhost"}).status_code == 200


# ------------------------------------------------------------------ history
def test_history(page, space):
    space.add("wallet", WALLET)
    assert page.get("/api/history/wallet").get_json() == []
    store.write_json(store.data_dir("wallet") / "history.json", [{"t": 1, "port": 1}])
    assert page.get("/api/history/wallet").get_json() == [{"t": 1, "port": 1}]
    assert page.get("/api/history/nothing").status_code == 404


# ----------------------------------------------------------------- the page
def test_until_the_page_is_built_it_says_so(page):
    r = page.get("/")
    assert r.status_code == 200 and b"The page isn't built yet" in r.data
    assert r.headers["X-Frame-Options"] == "DENY"


def test_the_built_page_is_served_and_nothing_outside_it(page, tmp_path):
    built = tmp_path / "no-page"
    built.mkdir()
    (built / "index.html").write_text("<h1>the page</h1>")
    (built / "app.js").write_text("1")
    (tmp_path / "secret.txt").write_text("no")
    assert page.get("/").data == b"<h1>the page</h1>"
    assert page.get("/app.js").data == b"1"
    assert page.get("/missing.js").status_code == 404
    assert page.get("/../secret.txt").status_code == 404
    assert page.get("/api/nothing").get_json()["error"]


# ------------------------------------------------------- what needs you
def entry(output_items, watch=(), settings=None, enabled=True, **output):
    return {"id": "p", "enabled": enabled, "watch": list(watch), "settings": settings or {},
            "output": {"ok": True, "items": output_items, **output}}


GOOD = {"key": "a", "name": "A", "value": "on", "state": "good"}
AMBER = {"key": "a", "name": "A", "value": 91, "unit": "%", "state": "warn", "note": "Nearly full"}
RED = {"key": "a", "name": "A", "value": "off", "state": "bad"}


def test_nothing_needs_you_while_what_you_watch_is_good():
    assert server.needs([entry([GOOD], watch=["a"])]) == []


def test_a_watched_item_that_turns_amber_or_red_needs_you():
    assert server.needs([entry([AMBER], watch=["a"])]) == [
        {"plugin": "p", "key": "a", "path": ["a"], "name": "A", "why": "warn", "value": 91, "unit": "%", "note": "Nearly full"}]
    assert server.needs([entry([RED], watch=["a"])])[0]["why"] == "bad"


def test_amber_and_red_you_dont_watch_stay_out_of_the_line():
    assert server.needs([entry([AMBER, {**RED, "key": "b"}])]) == []


def test_a_watched_item_that_goes_missing_needs_you_under_your_name_for_it():
    settings = {"items": {"obsidian": {"name": "My vault", "watch": True}}}
    assert server.needs([entry([], settings=settings)]) == [
        {"plugin": "p", "key": "obsidian", "path": ["obsidian"], "name": "My vault", "why": "missing"}]


def test_when_the_plugin_broke_what_it_watches_is_missing_and_says_why():
    (need,) = server.needs([entry([], watch=["a"], ok=False, error="It took longer than 10 s.")])
    assert (need["why"], need["note"]) == ("missing", "It took longer than 10 s.")


def test_your_choice_wins_over_what_the_plugin_watches():
    assert server.needs([entry([RED], watch=["a"], settings={"items": {"a": {"watch": False}}})]) == []
    assert server.needs([entry([RED], watch=["a"], settings={"items": {"a": {"hidden": True}}})]) == []


def test_a_plugin_thats_off_or_hasnt_run_needs_nothing():
    assert server.needs([entry([RED], watch=["a"], enabled=False)]) == []
    assert server.needs([{"id": "p", "enabled": True, "watch": ["a"], "settings": {}, "output": None}]) == []


def test_a_watched_part_of_an_item():
    settings = {"items": {"wallet": {"items": {"web": {"name": "Screens", "watch": True}}}}}
    wallet = {"key": "wallet", "name": "wallet", "state": "good", "items": [{"key": "web", "name": "web", "state": "bad"}]}
    assert server.needs([entry([wallet], settings=settings)]) == [
        {"plugin": "p", "key": "web", "path": ["wallet", "web"], "name": "Screens", "why": "bad"}]


def test_status_says_what_needs_you(page, space):
    space.add("wallet", WALLET + "watch: [port, nothing-like-this]\ntiles: [port]\n")
    run_once()
    body = page.get("/api/status").get_json()
    assert schemas.problems("status", body) == []
    assert body["plugins"][0]["watch"] == ["port", "nothing-like-this"] and body["plugins"][0]["tiles"] == ["port"]
    assert {"plugin": "wallet", "key": "nothing-like-this", "path": ["nothing-like-this"],
            "name": "nothing-like-this", "why": "missing"} in body["needs"]


def test_a_phone_can_fetch_the_icon_before_it_has_the_key(stranger, tmp_path):
    built = tmp_path / "no-page"
    built.mkdir()
    (built / "icon.svg").write_text("<svg/>")
    (built / "index.html").write_text("the page")
    assert stranger.get("/icon.svg").status_code == 200
    assert stranger.get("/").status_code == 401
    assert stranger.get("/index.html").status_code == 401
