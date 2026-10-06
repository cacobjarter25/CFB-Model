import os
import time
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BASE = "https://api.collegefootballdata.com"
_cache = {}


def _get(path, params, ttl=3600):
    key = (path, tuple(sorted(params.items())))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    k = os.environ.get("CFBD_API_KEY")
    if not k:
        return None
    try:
        r = requests.get(BASE + path, params=params,
                         headers={"Authorization": f"Bearer {k}"}, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    _cache[key] = (time.time(), data)
    return data


def _dt(s):
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def fmt_kickoff(iso):
    if not iso:
        return "TBD", ""
    dt = _dt(iso).astimezone(ZoneInfo("America/New_York"))
    return dt.strftime("%a %b %d"), dt.strftime("%I:%M %p").lstrip("0") + " ET"


def week_of(iso, season):
    """CFB week number that a kickoff time falls in, from the CFBD calendar."""
    cal = _get("/calendar", {"year": season}, ttl=86400)
    if not cal or not iso:
        return None
    dt = _dt(iso)
    best = None
    for w in cal:
        if w.get("seasonType", "regular") != "regular":
            continue
        start = w.get("firstGameStart") or w.get("startDate")
        if not start or w.get("week") is None:
            continue
        if _dt(start) <= dt and (best is None or w["week"] > best):
            best = w["week"]
    return best


def ap_top25(season):
    """Returns (poll_week, [{'rank', 'school', 'conference'}, ...])."""
    data = _get("/rankings", {"year": season, "seasonType": "regular"}, ttl=6 * 3600)
    if not data:
        return None, []
    latest = max(data, key=lambda w: w.get("week", 0))
    for p in latest.get("polls", []):
        if p.get("poll") == "AP Top 25":
            return latest.get("week"), p.get("ranks", [])
    return None, []