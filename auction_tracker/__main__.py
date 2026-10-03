"""Command line entry point.

    python -m auction_tracker run                 # daily: scrape, comps, evaluate, report, notify
    python -m auction_tracker scrape --backfill   # one-off: crawl history to seed the database
    python -m auction_tracker comps --backend chrome   # refresh market comps via your Chrome
    python -m auction_tracker evaluate            # re-score after editing config / overrides
    python -m auction_tracker check URL           # analyse a single bplelonglist listing now
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import bpl, db, history, notify, pipeline, report, transit
from .config import load_config
from .fetcher import Fetcher


def _fetcher(cfg, args) -> Fetcher:
    fcfg = dict(cfg.get("fetch", {}))
    if getattr(args, "backend", None):
        fcfg["backend"] = args.backend
    if getattr(args, "headless", False):
        fcfg["chrome_headless"] = True
    return Fetcher(fcfg)


def cmd_scrape(cfg, args, conn):
    with _fetcher(cfg, args) as f:
        pipeline.scrape(conn, f, cfg, backfill=args.backfill)


def cmd_comps(cfg, args, conn):
    with _fetcher(cfg, args) as f:
        n = pipeline.refresh_comps(conn, f, cfg, force=args.force, limit=args.limit)
    logging.info("refreshed comps for %d building(s)", n)


def cmd_evaluate(cfg, args, conn):
    results = pipeline.evaluate_all(conn, cfg, geocode=not args.no_geocode)
    _, bstats = history.load(conn)
    path = report.generate(results, bstats, cfg)
    ok = [e for e in results if e["status"] == "ok"]
    logging.info("evaluated %d active listings -> %s", len(ok), path)
    for e in ok[:10]:
        l = e["listing"]
        print(f"[{e['grade']}] {e['score']:5.1f}  {l['area_label']:<12} {str(l['building'] or l['title'])[:40]:<40} "
              f"RM{(l['reserve_price'] or 0):>10,.0f}  cover {e['finance'].get('rent_cover', '-')}  "
              f"max bid RM{e['max_bid'].get('max_bid') or 0:,}")
    return results


def cmd_run(cfg, args, conn):
    stats = {"search_pages": 0}
    with _fetcher(cfg, args) as f:
        try:
            stats = pipeline.scrape(conn, f, cfg)
        except Exception:
            logging.exception("scrape step failed; continuing with stored data")
        if not args.skip_comps:
            try:
                pipeline.refresh_comps(conn, f, cfg, limit=args.limit)
            except Exception:
                logging.exception("comps step failed; continuing with cached comps")
    results = cmd_evaluate(cfg, args, conn)
    sent = notify.notify(conn, results, cfg["scoring"].get("notify_min_grade", "A"))
    logging.info("notifications sent: %d", sent)
    if not stats.get("search_pages"):
        # Fail loudly (GitHub emails you) instead of silently going stale.
        logging.error("Could not load a single bplelonglist search page - site blocked or changed. "
                      "Dashboard was rebuilt from stored data only.")
        sys.exit(2)


def cmd_check(cfg, args, conn):
    """Fetch one listing, store it, fetch its comps and print the evaluation."""
    with _fetcher(cfg, args) as f:
        lst = bpl.parse_detail(f.get(args.url), args.url)
        label = pipeline.save_parsed(conn, lst, cfg)
        conn.commit()
        if not label:
            print(f"Note: listing area '{lst.area}' is outside your configured areas; evaluating anyway.")
            conn.execute("UPDATE listings SET area_label=? WHERE listing_id=?", (lst.area or "Other", lst.listing_id))
            conn.commit()
        pipeline.refresh_comps(conn, f, cfg)
    results = pipeline.evaluate_all(conn, cfg)
    for e in results:
        if e["listing"]["listing_id"] == lst.listing_id:
            print(json.dumps({k: e[k] for k in ("status", "grade", "score", "parts", "market_value", "rent_estimate",
                                                "finance", "max_bid", "station", "pros", "cons", "notes")},
                             indent=2, default=str))
            return
    print("Listing parsed but not evaluated (past auction date, too small or not residential):")
    print(json.dumps({k: v for k, v in lst.to_dict().items() if k != "raw_text"}, indent=2))


def cmd_reparse(cfg, args, conn):
    pipeline.reparse(conn, cfg)


def cmd_stations(cfg, args, conn):
    st = transit.load_stations(cfg["transit"]["bbox"], refresh=True)
    print(f"{len(st)} stations cached")


def main(argv=None):
    p = argparse.ArgumentParser(prog="auction_tracker", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", help="path to config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        sp.add_argument("--backend", choices=["http", "chrome", "auto"])
        sp.add_argument("--headless", action="store_true")
        return sp

    sp = add("run", cmd_run, "daily pipeline")
    sp.add_argument("--skip-comps", action="store_true", help="use cached comps only")
    sp.add_argument("--limit", type=int, help="max buildings to fetch comps for")
    sp.add_argument("--no-geocode", action="store_true")
    sp = add("scrape", cmd_scrape, "scrape bplelonglist")
    sp.add_argument("--backfill", action="store_true", help="crawl all pages to build history")
    sp = add("comps", cmd_comps, "refresh PropertyGuru / iProperty comps")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--limit", type=int)
    sp = add("evaluate", cmd_evaluate, "score listings and write the dashboard")
    sp.add_argument("--no-geocode", action="store_true")
    sp = add("check", cmd_check, "analyse one listing URL")
    sp.add_argument("url")
    add("reparse", cmd_reparse, "re-parse stored listing text")
    add("stations", cmd_stations, "refresh rail station cache")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    cfg = load_config(args.config)
    conn = db.connect()
    try:
        args.fn(cfg, args, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
