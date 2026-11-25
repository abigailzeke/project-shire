"""The standard format, written down once as JSON Schema.

The schemas beside this file say what a plugin.yaml may hold, what a
plugin's output looks like, how your choices and groups are saved, and what
the server answers the page. Shire checks against them here, and the page's
TypeScript types are made from the same files, so the two can't drift apart.
A problem comes back in plain words, because it goes onto the page."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

_KINDS = {"object": "a group of settings", "array": "a list", "string": "text", "integer": "a whole number",
          "number": "a number", "boolean": "true or false", "null": "empty"}


@cache
def _registry() -> Registry:
    """Every schema by its file name, so one can point to another, as the
    page's status points to a plugin's output."""
    found = []
    for file in resources.files(__package__).iterdir():
        if file.name.endswith(".schema.json"):
            found.append((file.name, Resource.from_contents(json.loads(file.read_text(encoding="utf-8")))))
    return Registry().with_resources(found)


@cache
def _validator(name: str) -> Draft202012Validator:
    text = resources.files(__package__).joinpath(f"{name}.schema.json").read_text(encoding="utf-8")
    return Draft202012Validator(json.loads(text), registry=_registry())


def _where(path) -> str:
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def _plain(error) -> str:
    where = _where(error.absolute_path)
    under = lambda key: f"{where}.{key}" if where else str(key)  # noqa: E731
    own = error.schema.get("x-plain") if isinstance(error.schema, dict) else None
    if own and error.validator != "type":
        return f"{where} {own}"
    if error.validator == "required":
        missing = [k for k in error.validator_value if k not in error.instance]
        return f"{under(missing[0])} is missing"
    if error.validator == "additionalProperties":
        known = error.schema.get("properties", {})
        extra = sorted(k for k in error.instance if k not in known)
        return f"{under(extra[0])} isn't something Shire knows"
    if error.validator == "enum":
        return f"{where} should be one of: {', '.join(str(v) for v in error.validator_value)}"
    if error.validator == "type":
        kinds = error.validator_value if isinstance(error.validator_value, list) else [error.validator_value]
        return f"{where or 'it'} should be {' or '.join(_KINDS.get(k, k) for k in kinds)}"
    return f"{where}: {error.message}" if where else error.message


def problems(name: str, value) -> list[str]:
    """Every way value breaks the schema called name, the nearest the top first."""
    errors = sorted(_validator(name).iter_errors(value), key=lambda e: (len(e.absolute_path), _where(e.absolute_path)))
    return [_plain(e) for e in errors]
