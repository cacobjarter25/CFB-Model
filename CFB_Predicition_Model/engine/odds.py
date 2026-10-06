import os
import time
import statistics
import requests

URL = "https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/odds"
CACHE_SECONDS = 300
_cache = {"t": 0, "data": None}


def fetch_odds():
    now = time.time()
    if _cache["data"] is not None and now - _cache["t"] < CACHE_SECONDS:
        return _cache["data"]
    r = requests.get(URL, params={
        "apiKey": os.environ["ODDS_API_KEY"],
        "regions": "us",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american",
    }, timeout=15)
    r.raise_for_status()
    _cache["t"], _cache["data"] = now, r.json()
    return _cache["data"]


def implied_prob(american):
    return 100 / (american + 100) if american > 0 else -american / (-american + 100)


def prob_to_american(p):
    if p >= 0.5:
        return round(-100 * p / (1 - p))
    return round(100 * (1 - p) / p)


def consensus(game):
    """Median spread/total across books, average implied moneyline probability."""
    home, away = game["home_team"], game["away_team"]
    spreads, totals, ml_h, ml_a = [], [], [], []
    for bk in game.get("bookmakers", []):
        for m in bk.get("markets", []):
            outs = {o["name"]: o for o in m["outcomes"]}
            if m["key"] == "spreads" and home in outs:
                spreads.append(outs[home]["point"])
            elif m["key"] == "totals" and "Over" in outs:
                totals.append(outs["Over"]["point"])
            elif m["key"] == "h2h" and home in outs and away in outs:
                ml_h.append(implied_prob(outs[home]["price"]))
                ml_a.append(implied_prob(outs[away]["price"]))
    med = lambda x: statistics.median(x) if x else None
    avg = lambda x: sum(x) / len(x) if x else None
    return {"home_spread": med(spreads), "total": med(totals),
            "ml_home_p": avg(ml_h), "ml_away_p": avg(ml_a)}