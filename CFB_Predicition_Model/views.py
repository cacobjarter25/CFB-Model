"""
Routes and views for the flask application.
"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import render_template, request
from CFB_Predicition_Model import app
from CFB_Predicition_Model.engine import picks
from CFB_Predicition_Model.engine.board import build_board
from CFB_Predicition_Model.engine.cfbd import ap_top25, week_of, fmt_kickoff
from CFB_Predicition_Model.engine.ratings import load_history, get_conference

CONF_PRIORITY = ["SEC", "Big Ten", "Big 12", "ACC"]


@app.template_filter('slug')
def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', str(value).lower()).strip('-')


def _conf_key(name):
    if name in CONF_PRIORITY:
        return (0, CONF_PRIORITY.index(name), name)
    if name == "Other":
        return (2, 0, name)
    return (1, 0, name)


def _row_confs(r):
    cs = {c for c in (get_conference(r["home"]), get_conference(r["away"])) if c}
    return sorted(cs) or ["Other"]


def _filter_rows(rows, show):
    if show == "ap":
        return [r for r in rows if r["home_rank"] or r["away_rank"]]
    if show != "all":
        return [r for r in rows if show in r["confs"]]
    return rows


def _by_day(rows):
    days = {}
    for r in rows:
        days.setdefault(r["day"], []).append(r)
    return list(days.items())


def _tally(vals):
    return {"w": vals.count("W"), "l": vals.count("L"), "p": vals.count("P")}


def _summary(rows):
    return {
        "ats": _tally([r["spread_pick"]["result"] for r in rows if r["spread_pick"]]),
        "ou": _tally([r["total_pick"]["result"] for r in rows if r["total_pick"]]),
        "su": _tally([r["su"] for r in rows]),
        "best": _tally([r["best"]["result"] for r in rows if r["best"]]),
    }


def _tracker(hweeks):
    """Units won betting 1u on every best bet, and on the top play only each week."""
    weeks, run_all, run_top, n_bets = [], 0.0, 0.0, 0
    for w in sorted(hweeks, key=int):
        games = [g for g in hweeks[w]["games"] if g.get("best")]
        res = [g["best"]["result"] for g in games]
        u_all = sum(picks.units(x) for x in res)
        top = max(games, key=lambda g: g["best"].get("ev", g["best"].get("edge", 0)),
                  default=None)
        u_top = picks.units(top["best"]["result"]) if top else 0.0
        run_all += u_all
        run_top += u_top
        n_bets += len(games)
        weeks.append({
            "week": int(w), "n": len(games),
            "w": res.count("W"), "l": res.count("L"), "p": res.count("P"),
            "units": u_all, "running": run_all,
            "top_label": top["best"]["label"] if top else None,
            "top_units": u_top, "top_running": run_top,
        })
    return {"weeks": weeks, "units": run_all, "top_units": run_top, "bets": n_bets,
            "roi": (run_all / n_bets) if n_bets else 0.0}


def _ap_panel(ap_list, rows):
    by_rank = {}
    for r in rows:
        if r["home_rank"]:
            by_rank[r["home_rank"]] = (r, "home")
        if r["away_rank"]:
            by_rank[r["away_rank"]] = (r, "away")
    out = []
    for t in ap_list:
        entry = {"rank": t["rank"], "school": t["school"],
                 "conf": t.get("conference"), "game": None}
        hit = by_rank.get(t["rank"])
        if hit:
            r, side = hit
            mine = r["model"]
            entry["game"] = {
                "where": "vs" if side == "home" else "at",
                "opp": r["away"] if side == "home" else r["home"],
                "day": r["day"],
                "vegas": r["v_home"] if side == "home" else r["v_away"],
                "model": (mine["m_home"] if side == "home" else mine["m_away"]) if mine else None,
                "best": bool(r["best"]),
            }
        out.append(entry)
    return out


@app.route('/')
@app.route('/home')
def home():
    view = request.args.get("view", "current")
    show = request.args.get("show", "all")

    year = datetime.now().year
    ap_week, ap_list = ap_top25(year)
    ranks = {r["school"]: r["rank"] for r in ap_list}

    history = load_history()
    hweeks = history.get("weeks", {})
    past_weeks = sorted(int(w) for w in hweeks)

    error, rows = None, []
    mode, week_num = "current", None

    if view.isdigit() and view in hweeks:
        mode, week_num = "past", int(view)
        rows = list(hweeks[view]["games"])
    else:
        view = "current"
        try:
            rows = build_board(ranks)
        except Exception as e:
            error = str(e)
        if rows:
            week_num = week_of(rows[0]["start"], year)

    rows.sort(key=lambda r: r["start"] or "")
    conf_counts = {}
    for r in rows:
        r.setdefault("ev", -1)
        r["day"], r["time"] = fmt_kickoff(r["start"])
        r["confs"] = _row_confs(r)
        for c in r["confs"]:
            conf_counts[c] = conf_counts.get(c, 0) + 1

    static_confs = app.config.get("STATIC_CONFS")
    if not static_confs and show not in ("all", "ap") and show not in conf_counts:
        show = "all"

    shown = _filter_rows(rows, show)
    filter_main = [
        {"value": "all", "label": "All games", "count": len(rows)},
        {"value": "ap", "label": "AP Top 25",
         "count": sum(1 for r in rows if r["home_rank"] or r["away_rank"])},
    ]
    conf_list = static_confs or sorted(conf_counts, key=_conf_key)
    filter_confs = [{"value": c, "label": c, "count": conf_counts.get(c, 0)}
                 for c in conf_list]

    top = sorted([r for r in shown if r["best"]],
                 key=lambda r: r["ev"], reverse=True)[:5] if mode == "current" else []
    ap_panel = _ap_panel(ap_list, rows) if (mode == "current" and show == "ap") else []
    summary = _summary(shown) if mode == "past" else None

    return render_template(
        'index.html', title='College Football Model', year=year,
        mode=mode, view=view, show=show, week_num=week_num,
        past_weeks=past_weeks, groups=_by_day(shown), n_shown=len(shown),
        filter_main=filter_main, filter_confs=filter_confs,
        top=top, ap_panel=ap_panel, ap_week=ap_week, summary=summary,
        tracker=_tracker(hweeks) if hweeks else None,
        overall=history.get("overall"), error=error,
        static_build=bool(app.config.get("STATIC_BUILD")),
        built_at=datetime.now(ZoneInfo("America/New_York")).strftime("%b %d, %I:%M %p ET"))


@app.route('/contact')
def contact():
    return render_template('contact.html', title='Contact',
                           year=datetime.now().year, message='Your contact page.')


@app.route('/about')
def about():
    return render_template('about.html', title='About',
                           year=datetime.now().year,
                           message='Your application description page.')