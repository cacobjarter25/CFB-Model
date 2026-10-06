import copy
import json
import os
import re
import statistics
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
sys.path.insert(0, HERE)

from CFB_Predicition_Model.engine.sim import project, simulate   # noqa: E402
from CFB_Predicition_Model.engine import picks                    # noqa: E402

DATA_DIR = os.path.join(HERE, "CFB_Predicition_Model", "data")
BASE = "https://api.collegefootballdata.com"
SEASONS = [2024, 2025, 2026]
CURRENT = 2026
HFA = 2.5        # PLACEHOLDERS: tune these
K = 0.08         # how fast ratings react to each game
REGRESS = 0.6    # how much ratings carry over between seasons
SPREAD_RE = re.compile(r"^(.*?)\s+([+-]?\d+(?:\.\d+)?)$")


def get(path, **params):
    key = os.environ.get("CFBD_API_KEY")
    if not key:
        raise SystemExit("CFBD_API_KEY is missing from your .env file.")
    r = requests.get(BASE + path, params=params,
                     headers={"Authorization": f"Bearer {key}"}, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_games():
    games, conf = [], {}
    for yr in SEASONS:
        rows = get("/games", year=yr, seasonType="regular", classification="fbs")
        for g in rows:
            if g.get("homeConference"):
                conf[g["homeTeam"]] = g["homeConference"]
            if g.get("awayConference"):
                conf[g["awayTeam"]] = g["awayConference"]
        done = [g for g in rows
                if g.get("homePoints") is not None and g.get("awayPoints") is not None]
        done.sort(key=lambda g: g["startDate"])
        for g in done:
            games.append((yr, g.get("week"), g["homeTeam"], g["awayTeam"],
                          g["homePoints"], g["awayPoints"], bool(g.get("neutralSite"))))
    return games, conf


def build(games):
    """Each team gets 'off' (points scored vs average) and 'def' (points
    allowed vs average; lower is better). Also snapshots the ratings
    before each week of the current season."""
    pts = [p for g in games for p in (g[4], g[5])]
    avg = sum(pts) / len(pts)
    teams, snaps, last = {}, {}, None
    for season, week, h, a, hp, ap, neutral in games:
        if last is not None and season != last:
            for v in teams.values():
                v["off"] *= REGRESS
                v["def"] *= REGRESS
        last = season
        if season == CURRENT and week not in snaps:
            snaps[week] = copy.deepcopy(teams)
        H = teams.setdefault(h, {"off": 0.0, "def": 0.0})
        A = teams.setdefault(a, {"off": 0.0, "def": 0.0})
        hfa = 0 if neutral else HFA
        exp_h = avg + H["off"] + A["def"] + hfa / 2
        exp_a = avg + A["off"] + H["def"] - hfa / 2
        eh, ea = hp - exp_h, ap - exp_a
        H["off"] += K * eh
        A["def"] += K * eh
        A["off"] += K * ea
        H["def"] += K * ea
    return avg, teams, snaps


def fetch_ap():
    out = {}
    try:
        for entry in get("/rankings", year=CURRENT, seasonType="regular"):
            for p in entry.get("polls", []):
                if p.get("poll") == "AP Top 25":
                    out[entry["week"]] = {r["school"]: r["rank"] for r in p["ranks"]}
    except Exception as e:
        print("Could not load AP rankings:", e)
    return out


def consensus_line(g):
    home, away = g["homeTeam"], g["awayTeam"]
    spreads, totals = [], []
    for ln in g.get("lines", []):
        m = SPREAD_RE.match(ln.get("formattedSpread") or "")
        if m:
            team, val = m.group(1), float(m.group(2))
            if team == home:
                spreads.append(val)
            elif team == away:
                spreads.append(-val)
        try:
            if ln.get("overUnder") is not None:
                totals.append(float(ln["overUnder"]))
        except (TypeError, ValueError):
            pass
    med = lambda x: statistics.median(x) if x else None
    return med(spreads), med(totals)


def tally(results):
    return {"w": results.count("W"), "l": results.count("L"), "p": results.count("P")}


def graded(b, hp, ap, hs, tot):
    if not b:
        return None
    return {"label": b["label"], "prob": round(b["prob"], 3),
            "edge": round(b["edge"], 3), "ev": round(b["ev"], 3), "result": picks.grade(b, hp, ap, hs, tot)}


def build_history(snaps, avg, ap_by_week):
    weeks, all_ats, all_ou, all_su, all_best = {}, [], [], [], []
    for w in sorted(k for k in snaps if k is not None and k >= 1):
        teams, ranks = snaps[w], ap_by_week.get(w, {})
        rows = []
        for g in get("/lines", year=CURRENT, week=w, seasonType="regular"):
            hp = g.get("homeScore", g.get("homePoints"))
            ap = g.get("awayScore", g.get("awayPoints"))
            if hp is None or ap is None:
                continue
            home, away = g["homeTeam"], g["awayTeam"]
            H, A = teams.get(home), teams.get(away)
            hs, tot = consensus_line(g)
            if not H or not A or (hs is None and tot is None):
                continue
            mm, tm = project(H, A, avg, hs, tot)
            s = simulate(mm, tm, hs, tot)
            bets = picks.candidates(home, away, hs, tot, None, None, s)
            best = picks.best_bet(bets)
            hc, ac = g.get("homeConference"), g.get("awayConference")
            rows.append({
                "home": home, "away": away, "start": g.get("startDate"),
                "conf": hc or "Other", "nonconf": hc != ac,
                "home_rank": ranks.get(home), "away_rank": ranks.get(away),
                "hs": hs, "tot": tot,
                "v_home": picks.fmt_sp(hs),
                "v_away": picks.fmt_sp(None if hs is None else -hs),
                "model": picks.model_summary(home, away, s),
                "best": graded(best, hp, ap, hs, tot),
                "ev": best["ev"] if best else -1,
                "spread_pick": graded(picks.lean(bets, "spread"), hp, ap, hs, tot),
                "total_pick": graded(picks.lean(bets, "total"), hp, ap, hs, tot),
                "su": "W" if (hp > ap) == (s["home_win"] > 0.5) else "L",
                "final": {"home": hp, "away": ap},
            })
        ats = [r["spread_pick"]["result"] for r in rows if r["spread_pick"]]
        ou = [r["total_pick"]["result"] for r in rows if r["total_pick"]]
        su = [r["su"] for r in rows]
        bb = [r["best"]["result"] for r in rows if r["best"]]
        all_ats += ats; all_ou += ou; all_su += su; all_best += bb
        weeks[str(w)] = {"games": rows, "summary": {
            "ats": tally(ats), "ou": tally(ou), "su": tally(su), "best": tally(bb)}}
        print(f"Week {w}: {len(rows)} games | spread {tally(ats)} | O/U {tally(ou)} | winners {tally(su)}")
    return {"season": CURRENT, "updated": datetime.now().isoformat(timespec="seconds"),
            "weeks": weeks,
            "overall": {"ats": tally(all_ats), "ou": tally(all_ou),
                        "su": tally(all_su), "best": tally(all_best)}}

def fetch_logos():
    out = {}
    try:
        for t in get("/teams/fbs", year=CURRENT):
            logos = t.get("logos") or []
            if logos:
                out[t["school"]] = logos[0].replace("http://", "https://")
    except Exception as e:
        print("Could not load team logos:", e)
    return out


if __name__ == "__main__":
    games, conf = fetch_games()
    avg, teams, snaps = build(games)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "ratings.json"), "w", encoding="utf-8") as f:
        json.dump({"league_avg": round(avg, 2), "conferences": conf,
                   "teams": {t: {"off": round(v["off"], 2), "def": round(v["def"], 2)}
                             for t, v in teams.items()}}, f, indent=1)
    print(f"Ratings: {len(games)} games, {len(teams)} teams, avg {avg:.1f} pts/team")

    history = build_history(snaps, avg, fetch_ap())
    with open(os.path.join(DATA_DIR, "history.json"), "w", encoding="utf-8") as f:
        json.dump(history, f)
    print("Overall:", history["overall"])