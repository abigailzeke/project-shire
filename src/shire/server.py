"""The server: the part of Shire your phone talks to.

It serves the page, and answers the page's questions from what's in your
space. It never calls the scheduler. The scheduler writes data/ and the
server reads it, and the server writes user-settings/ and the scheduler reads it,
so either can stop without the other.

    GET /api/status            everything at once: every plugin, what it
                               last found, your choices, and your groups
    GET /api/history/<plugin>  that plugin's last 24 hours
    PUT /api/settings/<plugin> saves your choices for one plugin
    PUT /api/groups            saves your groups

The server only ever writes into user-settings/. It can't change a plugin or add
one, so the most anyone holding your key can do is switch a plugin of yours
on or off.

Everything is behind your key. Open the page once with ?key=… and a cookie
remembers that phone for a year."""

from __future__ import annotations

import hmac
import time
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, redirect, request, send_from_directory
from werkzeug.exceptions import HTTPException

from . import __version__, host, plugins, scheduler, schemas, store

COOKIE = "shire"
YEAR = 365 * 86400
# What a phone asks for before it has the key, when the page is put on its
# home screen. There's nothing of yours in them.
PUBLIC = {"/manifest.webmanifest", "/icon.svg", "/apple-touch-icon.png"}

_SHELL = """<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Project Shire</title>
<body style="font:16px/1.5 -apple-system,system-ui,sans-serif;max-width:22rem;margin:22vh auto 0;padding:0 1.5rem">
<p style="font:italic 22px Baskerville,Georgia,serif;margin:0 0 20px">LINE</p>
BELOW
</body></html>"""
_KEY_BOX = """<form method="get" action="/">
<input name="key" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false"
 placeholder="key" autofocus style="font:inherit;width:100%;box-sizing:border-box;padding:.6rem .8rem;
 border:1px solid #8886;border-radius:.6rem;background:transparent;color:inherit">
</form>"""


def _shell(line: str, below: str = "") -> str:
    return _SHELL.replace("LINE", line).replace("BELOW", below)


def page_dir() -> Path:
    """The built page, which travels inside the package."""
    return Path(__file__).parent / "page"


def key_ok(given) -> bool:
    return bool(given) and hmac.compare_digest(str(given).encode(), store.key().encode())


def default_groups() -> list[dict]:
    """The three groups a fresh install comes with."""
    return [
        {"id": "computer", "name": "Your Mac" if host.SYSTEM == "macos" else "Your computer",
         "plugins": ["core-os-metrics", "core-apps", "core-scripts", "core-jobs"]},
        {"id": "agent", "name": "Your agent", "colour": "lilac",
         "plugins": ["core-claude-code", "core-connectors", "core-obsidian"]},
        {"id": "docker", "name": "Docker", "plugins": ["core-docker"]},
    ]


def _read(path, schema: str, default):
    """A JSON file from your space, or default when it's missing or isn't
    in its format."""
    found = store.read_json(path)
    return default if found is None or schemas.problems(schema, found) else found


def groups() -> list[dict]:
    found = _read(store.groups_path(), "groups", None)
    return default_groups() if found is None else found


def _watched(plugin: dict, choices: dict, items: list, defaults, gone, found: list, path: tuple = ()) -> None:
    live = {item["key"]: item for item in items}
    for key in dict.fromkeys([*defaults, *choices]):
        choice = choices.get(key, {})
        if choice.get("hidden"):
            continue
        item = live.get(key)
        if choice.get("watch", key in defaults):
            entry = {"plugin": plugin["id"], "key": key, "path": [*path, key],
                     "name": choice.get("name") or (item or {}).get("name") or key}
            if item is None:
                found.append({**entry, "why": "missing", **({"note": gone} if gone else {})})
            elif item.get("state") in ("warn", "bad"):
                found.append({**entry, "why": item["state"],
                              **{k: item[k] for k in ("value", "unit", "note") if item.get(k) is not None}})
        if choice.get("items"):
            _watched(plugin, choice["items"], (item or {}).get("items", []), (), gone, found, (*path, key))


def needs(entries: list[dict]) -> list[dict]:
    """What the snapshot's line speaks up for: every item you watch that has
    turned amber, turned red or gone missing. A plugin that's off, or hasn't
    run yet, is left out, and so is anything you've hidden."""
    found: list[dict] = []
    for plugin in entries:
        output = plugin["output"]
        if plugin["enabled"] and output is not None:
            gone = output.get("error") or output.get("reason")
            _watched(plugin, plugin["settings"].get("items", {}), output["items"], plugin["watch"], gone, found)
    return found


def status() -> dict:
    """Everything the page shows, in one answer."""
    found = []
    for plugin in plugins.find().values():
        config = plugin.config if plugin.problem is None else {}
        on = scheduler.enabled(plugin)
        entry = {
            "id": plugin.id,
            "name": plugin.name,
            "core": plugin.core,
            "enabled": on,
            "display": config.get("display", "list"),
            "every": plugin.every,
            "history": config.get("history", []),
            "watch": config.get("watch", []),
            "tiles": config.get("tiles", []),
            "settings": _read(store.settings_path(plugin.id), "settings", {}),
            # What an off plugin found before it was switched off is old news.
            "output": _read(store.data_dir(plugin.id) / "output.json", "output", None) if on else None,
        }
        if config.get("description"):
            entry["description"] = config["description"]
        if plugin.problem:
            entry["problem"] = plugin.problem
        found.append(entry)
    return {
        "shire": {"version": __version__, "now": int(time.time()), "system": host.SYSTEM_NAME},
        "groups": groups(),
        "needs": needs(found),
        "plugins": found,
    }


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024
    app.json.sort_keys = False

    def is_api() -> bool:
        return request.path.startswith("/api/")

    def locked(line: str = "This page is locked. Open your link once, or enter the key."):
        return Response(_shell(line, _KEY_BOX), status=401, mimetype="text/html")

    @app.before_request
    def gate():
        given = request.args.get("key")
        if given is not None and request.method == "GET" and not is_api():
            # A key in the link: check it, remember this phone, and take the
            # key out of the address bar.
            if not key_ok(given):
                return locked("That isn't the key. Open your link once, or enter the key.")
            answer = redirect("/", 303)
            answer.set_cookie(COOKIE, given, max_age=YEAR, httponly=True, samesite="Lax", secure=request.is_secure)
            return answer
        if key_ok(request.cookies.get(COOKIE)):
            return None
        if request.method == "GET" and request.path in PUBLIC:
            return None
        if is_api():
            return jsonify(error="This needs your key."), 401
        return locked()

    @app.after_request
    def careful(answer):
        answer.headers["X-Content-Type-Options"] = "nosniff"
        answer.headers["X-Frame-Options"] = "DENY"
        answer.headers["Referrer-Policy"] = "no-referrer"
        answer.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
        if is_api():
            answer.headers["Cache-Control"] = "no-store"
        return answer

    @app.errorhandler(HTTPException)
    def plainly(error):
        if is_api():
            return jsonify(error=error.description), error.code
        return error

    def sent():
        """What the page sent, or the answer that says why it can't be used.
        Only the page itself may save: a browser tells us where a request
        came from, and another site's is turned away."""
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            return None, (jsonify(error="That came from another site."), 403)
        if not request.is_json:
            return None, (jsonify(error="Send it as JSON."), 415)
        value = request.get_json(silent=True)
        if value is None:
            return None, (jsonify(error="That isn't JSON."), 400)
        return value, None

    def known(plugin_id: str) -> bool:
        return plugin_id in plugins.find()

    def no_plugin(plugin_id: str):
        return jsonify(error=f"Shire has no plugin called {plugin_id}."), 404

    # ------------------------------------------------- what the page asks
    @app.get("/api/status")
    def get_status():
        return jsonify(status())

    @app.get("/api/history/<plugin_id>")
    def get_history(plugin_id):
        if not known(plugin_id):
            return no_plugin(plugin_id)
        points = store.read_json(store.data_dir(plugin_id) / "history.json", [])
        return jsonify(points if isinstance(points, list) else [])

    @app.put("/api/settings/<plugin_id>")
    def put_settings(plugin_id):
        if not known(plugin_id):
            return no_plugin(plugin_id)
        settings, refusal = sent()
        if refusal:
            return refusal
        found = schemas.problems("settings", settings)
        if found:
            return jsonify(error=found[0]), 400
        store.write_json(store.settings_path(plugin_id), settings)
        return jsonify(settings)

    @app.put("/api/groups")
    def put_groups():
        value, refusal = sent()
        if refusal:
            return refusal
        found = schemas.problems("groups", value)
        if found:
            return jsonify(error=found[0]), 400
        store.write_json(store.groups_path(), value)
        return jsonify(value)

    # ------------------------------------------------------------ the page
    @app.get("/")
    def index():
        if (page_dir() / "index.html").is_file():
            return send_from_directory(page_dir(), "index.html")
        return Response(_shell("Shire is running. The page isn't built yet."), mimetype="text/html")

    @app.get("/<path:name>")
    def asset(name):
        return send_from_directory(page_dir(), name)

    return app


def listen(where: str, port: int):
    """The server, already holding its port. Its run() answers until its
    close() is called."""
    from waitress import create_server
    return create_server(create_app(), host=where, port=port, threads=4, ident="shire")
