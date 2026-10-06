BREAKEVEN_110 = 110 / 210   # 52.38%: break-even at -110
MIN_EV = 0.05               # minimum expected profit per 1u risked (about a 55% win chance at -110)
MAX_PROB = 0.62             # ignore model probabilities above this: usually model error, not edge
ML_MIN_P, ML_MAX_P = 0.43, 0.57   # moneylines only count when priced near even money


def fmt_sp(x):
    if x is None:
        return "-"
    if abs(x) < 0.05:
        return "PK"
    return f"{x:+.1f}"


def spread_text(home, away, hs):
    if hs is None:
        return None
    if hs == 0:
        return "PK"
    fav = home if hs < 0 else away
    return f"{fav} -{abs(hs):.1f}"


def _line(team, pts):
    return f"{team} PK" if pts == 0 else f"{team} {pts:+.1f}"


def _bet(kind, side, label, prob, breakeven):
    return {"kind": kind, "side": side, "label": label, "prob": prob,
            "edge": prob - breakeven, "ev": prob / breakeven - 1}


def candidates(home, away, hs, tot, ml_home_p, ml_away_p, s):
    bets = []
    if hs is not None:
        bets.append(_bet("spread", "home", _line(home, hs), s["home_cover"], BREAKEVEN_110))
        bets.append(_bet("spread", "away", _line(away, -hs), s["away_cover"], BREAKEVEN_110))
    if tot is not None:
        bets.append(_bet("total", "over", f"Over {tot}", s["over"], BREAKEVEN_110))
        bets.append(_bet("total", "under", f"Under {tot}", s["under"], BREAKEVEN_110))
    if ml_home_p and ML_MIN_P <= ml_home_p <= ML_MAX_P:
        bets.append(_bet("ml", "home", f"{home} ML", s["home_win"], ml_home_p))
    if ml_away_p and ML_MIN_P <= ml_away_p <= ML_MAX_P:
        bets.append(_bet("ml", "away", f"{away} ML", 1 - s["home_win"], ml_away_p))
    return bets


def best_bet(bets):
    ok = [b for b in bets if b["ev"] >= MIN_EV and b["prob"] <= MAX_PROB]
    return max(ok, key=lambda b: b["ev"]) if ok else None


def lean(bets, kind):
    """The model's side of a market, regardless of edge size."""
    c = [b for b in bets if b["kind"] == kind]
    return max(c, key=lambda x: x["prob"]) if c else None


def grade(bet, home_pts, away_pts, hs, tot):
    margin = home_pts - away_pts
    total = home_pts + away_pts
    kind, side = bet["kind"], bet["side"]
    if kind == "spread":
        v = margin + hs
        if v == 0:
            return "P"
        return "W" if (v > 0) == (side == "home") else "L"
    if kind == "total":
        if total == tot:
            return "P"
        return "W" if (total > tot) == (side == "over") else "L"
    return "W" if (margin > 0) == (side == "home") else "L"


def units(result, breakeven=BREAKEVEN_110):
    """Profit in units from risking 1u at the given price (default -110)."""
    if result == "W":
        return 1 / breakeven - 1
    if result == "L":
        return -1.0
    return 0.0


def model_summary(home, away, s):
    m = s["mean_margin"]
    fav = home if m >= 0 else away
    return {
        "spread": f"{fav} -{abs(m):.1f}",
        "margin": m,
        "m_home": fmt_sp(-m),
        "m_away": fmt_sp(m),
        "total": f"{s['mean_total']:.1f}",
        "proj_home": s["home_pts"],
        "proj_away": s["away_pts"],
        "home_win": s["home_win"],
    }