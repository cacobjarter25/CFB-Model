import numpy as np

rng = np.random.default_rng()

# PLACEHOLDERS: calibrate these by backtesting against past results.
HFA = 2.5            # home-field advantage in points
SD_MARGIN = 17.0     # game-to-game noise in the final margin
SD_TOTAL = 13.0      # game-to-game noise in the combined score
MODEL_WEIGHT = 0.5   # 1.0 = trust the model fully, 0.0 = just echo the market


def project(home, away, avg, market_spread, market_total):
    """Expected margin (home perspective) and total from team ratings,
    shrunk toward the market by (1 - MODEL_WEIGHT)."""
    raw_margin = (home["off"] + away["def"]) - (away["off"] + home["def"]) + HFA
    raw_total = 2 * avg + home["off"] + away["def"] + away["off"] + home["def"]
    margin_mu, total_mu = raw_margin, raw_total
    if market_spread is not None:
        margin_mu = MODEL_WEIGHT * raw_margin + (1 - MODEL_WEIGHT) * (-market_spread)
    if market_total is not None:
        total_mu = MODEL_WEIGHT * raw_total + (1 - MODEL_WEIGHT) * market_total
    return margin_mu, total_mu


def simulate(margin_mu, total_mu, market_spread, market_total, n=20000):
    margin = rng.normal(margin_mu, SD_MARGIN, n)
    total = rng.normal(total_mu, SD_TOTAL, n)
    home_pts = np.clip((total + margin) / 2, 0, None)
    away_pts = np.clip((total - margin) / 2, 0, None)
    margin, total = home_pts - away_pts, home_pts + away_pts

    out = {
        "home_win": float((margin > 0).mean()),
        "home_pts": float(home_pts.mean()),
        "away_pts": float(away_pts.mean()),
        "mean_margin": float(margin.mean()),
        "mean_total": float(total.mean()),
    }
    if market_spread is not None:
        out["home_cover"] = float((margin + market_spread > 0).mean())
        out["away_cover"] = float((margin + market_spread < 0).mean())
    if market_total is not None:
        out["over"] = float((total > market_total).mean())
        out["under"] = float((total < market_total).mean())
    return out