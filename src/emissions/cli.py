"""Command line entry point.

emissions migrate                      # create/upgrade the schema, sync reference data
emissions ingest                       # all sources
emissions ingest --source eurostat     # one source
emissions serve --port 8000
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

import httpx

from emissions import __version__
from emissions.config import Settings
from emissions.db.repository import make_engine, normalise_db_url, sync_reference_data
from emissions.landing import LocalLandingStore
from emissions.pipeline import ADAPTERS, run_source

log = logging.getLogger("emissions")


def migrate(settings: Settings) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()  # migrations ship inside the package, so this also works in Docker
    cfg.set_main_option("script_location", "emissions:migrations")
    # "%" must be escaped in Alembic's ini-style config (passwords can contain it).
    cfg.set_main_option(
        "sqlalchemy.url", normalise_db_url(settings.database_url).replace("%", "%%")
    )
    command.upgrade(cfg, "head")
    engine = make_engine(settings.database_url)
    with engine.begin() as conn:
        sync_reference_data(conn)
    print("database is up to date; reference data synced")


def ingest(settings: Settings, sources: list[str]) -> int:
    engine = make_engine(settings.database_url)
    landing = LocalLandingStore(settings.landing_dir)
    failed = []
    with httpx.Client(
        timeout=settings.http_timeout_s,
        follow_redirects=True,
        headers={"User-Agent": f"climate-emissions-platform/{__version__}"},
    ) as http:
        for code in sources:
            try:
                r = run_source(
                    ADAPTERS[code],
                    engine=engine,
                    http=http,
                    landing=landing,
                    today=datetime.now(UTC).date(),
                )
            except Exception as exc:  # one broken source must not stop the others
                failed.append(code)
                print(f"{code:10s} FAILED  {exc}", file=sys.stderr)
                continue
            dropped = sum(r.report.dropped.values())
            print(
                f"{code:10s} run {r.run_id}: parsed {r.parsed:>6}  dropped {dropped:>6}  "
                f"rejected {r.rejected:>4}  loaded {r.valid:>6}  "
                f"(+{r.stats.inserted} new, {r.stats.updated} changed, "
                f"{r.stats.unchanged} unchanged)  warnings {len(r.report.warnings)}"
            )
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="emissions", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="create or upgrade the database schema")
    ing = sub.add_parser("ingest", help="download, validate and load source data")
    ing.add_argument(
        "--source",
        choices=sorted(ADAPTERS),
        action="append",
        help="repeatable; default: all sources",
    )
    srv = sub.add_parser("serve", help="run the REST API")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    settings = Settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if args.command == "migrate":
        migrate(settings)
        return 0
    if args.command == "ingest":
        return ingest(settings, args.source or list(ADAPTERS))

    import uvicorn

    uvicorn.run("emissions.main:app", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
