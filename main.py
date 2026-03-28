"""Alpha Vault CLI entry-point."""
from __future__ import annotations

import argparse
import sys


def cmd_serve(args):
    from pipeline.config import get_config
    cfg = get_config()

    if cfg.scheduler.enabled:
        from pipeline.scheduler import start_scheduler
        start_scheduler(
            us_time=cfg.scheduler.us_run_time,
            hk_time=cfg.scheduler.hk_run_time,
        )

    import uvicorn
    uvicorn.run(
        "api.server:app",
        host=args.host, port=args.port,
        reload=args.reload,
    )


def cmd_bootstrap(args):
    from core.user import UserManager
    um = UserManager()
    try:
        user = um.bootstrap_admin(args.username, args.password)
        print(f"Admin created: {user.username}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        um.close()


def cmd_screen(args):
    from pipeline.screening import run_screening
    results = run_screening(market=args.market, top_n=args.top_n)
    print(f"Screened {len(results)} stocks for {args.market}:")
    for r in results[:10]:
        print(f"  {r['ticker']:>8} {r['name']:<30} score={r['score']:.1f}")


def cmd_run(args):
    from pipeline.runner import run_daily_pipeline
    print(f"Running pipeline for {args.market}...")
    result = run_daily_pipeline(
        market=args.market,
        force=args.force,
        trigger_source="cli_manual",
    )
    if result.get("skipped"):
        print(f"Skipped: {result.get('reason', 'already ran')}")
    else:
        print(f"Done: {result.get('published_count', 0)} recommendations published")
        print(f"  ref_date: {result.get('ref_date')}")
        print(f"  candidates: {result.get('candidate_count', 0)}")


def cmd_build_pool(args):
    from core.data_source import get_index_components
    from pipeline.config import get_config
    import json

    cfg = get_config()
    all_stocks = []
    for market, entries in cfg.stock_pool.items():
        for entry in entries:
            print(f"Fetching {entry.name} ({entry.index})...")
            components = get_index_components(entry.index)
            print(f"  Got {len(components)} components")
            all_stocks.extend(components)

    seen = set()
    unique = []
    for s in all_stocks:
        key = (s["ticker"], s["market"])
        if key not in seen:
            seen.add(key)
            unique.append(s)

    out_path = "data/stock_pool.json"
    import os
    os.makedirs("data", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(unique)} stocks to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Alpha Vault CLI")
    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="Start the API server (with optional scheduler)")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")

    p_boot = sub.add_parser("bootstrap", help="Create admin user")
    p_boot.add_argument("--username", required=True)
    p_boot.add_argument("--password", required=True)

    p_screen = sub.add_parser("screen", help="Run stock screening")
    p_screen.add_argument("--market", default="us_stock", choices=["us_stock", "hk_stock"])
    p_screen.add_argument("--top-n", type=int, default=20)

    p_run = sub.add_parser("run", help="Run daily pipeline for a single market")
    p_run.add_argument("--market", required=True, choices=["us_stock", "hk_stock"])
    p_run.add_argument("--force", action="store_true", help="Force re-run even if already ran today")

    p_pool = sub.add_parser("build-pool", help="Build stock pool from index components")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    cmds = {
        "serve": cmd_serve,
        "bootstrap": cmd_bootstrap,
        "screen": cmd_screen,
        "run": cmd_run,
        "build-pool": cmd_build_pool,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
