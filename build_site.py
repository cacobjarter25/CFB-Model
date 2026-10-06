import copy
import os
import shutil
import sys
from datetime import datetime

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
sys.path.insert(0, HERE)

from CFB_Predicition_Model import app, views                      # noqa: E402
from CFB_Predicition_Model.engine.board import build_board         # noqa: E402
from CFB_Predicition_Model.engine.cfbd import ap_top25             # noqa: E402
from CFB_Predicition_Model.engine.ratings import load_history      # noqa: E402

OUT = os.path.join(HERE, "site")


def fix_paths(html):
    """Make links relative so the site works under github.io/<repo>/."""
    html = html.replace('href="/static/', 'href="static/').replace('src="/static/', 'src="static/')
    for old, new in (('href="/home"', 'href="index.html"'),
                     ('href="/about"', 'href="about.html"'),
                     ('href="/contact"', 'href="contact.html"'),
                     ('href="/"', 'href="index.html"')):
        html = html.replace(old, new)
    return html


def write(name, html):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(html)


def main():
    year = datetime.now().year
    _, ap_list = ap_top25(year)
    ranks = {r["school"]: r["rank"] for r in ap_list}

    # One live odds fetch, reused for every page so all pages agree.
    board = build_board(ranks)
    views.build_board = lambda _ranks: copy.deepcopy(board)

    history = load_history()
    weeks = sorted(int(w) for w in history.get("weeks", {}))

    confs = set()
    for r in board:
        confs.update(views._row_confs(r))
    for w in weeks:
        for r in history["weeks"][str(w)]["games"]:
            confs.update(views._row_confs(r))

    app.config["STATIC_BUILD"] = True
    app.config["STATIC_CONFS"] = sorted(confs, key=views._conf_key)

    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    shutil.copytree(os.path.join(HERE, "CFB_Predicition_Model", "static"),
                    os.path.join(OUT, "static"))
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    client = app.test_client()
    shows = ["all", "ap"] + app.config["STATIC_CONFS"]
    n = 0
    for v in ["current"] + [str(w) for w in weeks]:
        for s in shows:
            res = client.get("/", query_string={"view": v, "show": s})
            if res.status_code != 200:
                raise SystemExit(f"Page failed (view={v}, show={s}): HTTP {res.status_code}")
            name = "index.html" if (v == "current" and s == "all") else f"{v}-{views.slug(s)}.html"
            write(name, fix_paths(res.get_data(as_text=True)))
            n += 1
    for route, name in (("/about", "about.html"), ("/contact", "contact.html")):
        write(name, fix_paths(client.get(route).get_data(as_text=True)))
    print(f"Built {n + 2} pages in {OUT}")


if __name__ == "__main__":
    main()