import json
import os

_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_files = {}


def _load(name):
    path = os.path.join(_DIR, name)
    try:
        m = os.path.getmtime(path)
    except OSError:
        return {}
    hit = _files.get(name)
    if not hit or hit[0] != m:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _files[name] = (m, data)
        return data
    return hit[1]


def match(name, table):
    """Exact match, else the longest key that prefixes the odds-API name
    (e.g. 'Texas A&M Aggies' -> 'Texas A&M')."""
    if name in table:
        return table[name]
    best = None
    for k in table:
        if name.startswith(k) and (best is None or len(k) > len(best)):
            best = k
    return table[best] if best else None


def league_avg():
    return _load("ratings.json").get("league_avg", 28.0)


def get_team(name):
    return match(name, _load("ratings.json").get("teams", {}))


def get_conference(name):
    return match(name, _load("ratings.json").get("conferences", {}))


def get_logo(name):
    return match(name, _load("ratings.json").get("logos", {}))


def load_history():
    return _load("history.json")