from .odds import fetch_odds, consensus, prob_to_american
from .ratings import get_team, league_avg, get_conference, match
from .sim import project, simulate
from . import picks


def build_board(ranks):
    avg = league_avg()
    rows = []
    for g in sorted(fetch_odds(), key=lambda x: x["commence_time"]):
        home, away = g["home_team"], g["away_team"]
        c = consensus(g)
        hs, tot = c["home_spread"], c["total"]
        h, a = get_team(home), get_team(away)
        hc, ac = get_conference(home), get_conference(away)

        row = {
            "home": home, "away": away, "start": g["commence_time"],
            "conf": hc or "Other", "nonconf": hc != ac,
            "home_rank": match(home, ranks), "away_rank": match(away, ranks),
            "hs": hs, "tot": tot,
            "v_home": picks.fmt_sp(hs),
            "v_away": picks.fmt_sp(None if hs is None else -hs),
            "ml_home": prob_to_american(c["ml_home_p"]) if c["ml_home_p"] else None,
            "ml_away": prob_to_american(c["ml_away_p"]) if c["ml_away_p"] else None,
            "model": None, "best": None, "ev": -1,
        }
        if h and a:
            margin_mu, total_mu = project(h, a, avg, hs, tot)
            s = simulate(margin_mu, total_mu, hs, tot)
            row["model"] = picks.model_summary(home, away, s)
            bets = picks.candidates(home, away, hs, tot, c["ml_home_p"], c["ml_away_p"], s)
            b = picks.best_bet(bets)
            if b:
                row["best"] = dict(b, game=f"{away} @ {home}")
                row["ev"] = b["ev"]
        rows.append(row)
    return rows