"""`bastion` command line: ingest, fixtures, build."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from bastion import paths


def _cmd_ingest(args: argparse.Namespace) -> int:
    from bastion.ingest.base import HttpClient, Pins, materialise
    from bastion.ingest.registry import CORE, SOURCES

    names = CORE if args.source == "core" else [s.strip() for s in args.source.split(",")]
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        print(f"unknown source(s): {unknown}; known: {sorted(SOURCES)}", file=sys.stderr)
        return 2
    quarters = [q.strip() for q in args.quarters.split(",")] if args.quarters else []
    client = HttpClient()
    pins = Pins.load()
    raw = paths.raw_root()
    for name in names:
        items = SOURCES[name](client, quarters)
        for res in materialise(items, raw, pins, pin=args.pin, allow_drift=args.allow_drift):
            print(f"{res.status:13s} {res.nbytes:>12,d}  {res.sha256[:16]}  {res.relpath}")
    return 0


def _cmd_fixtures(args: argparse.Namespace) -> int:
    from bastion import fixtures

    if args.check:
        diffs = fixtures.check(paths.FIXTURE_RAW)
        if diffs:
            print("fixtures differ from their generator:", *diffs, sep="\n  ", file=sys.stderr)
            return 1
        print("fixtures match generator")
        return 0
    for rel in fixtures.write_all(paths.FIXTURE_RAW):
        print("wrote", rel)
    return 0


def run_dbt(target: str, command: str = "build", extra: list[str] | None = None) -> bool:
    from dbt.cli.main import dbtRunner

    raw = paths.FIXTURE_RAW if target == "ci" else paths.raw_root()
    db = paths.warehouse_path(target)
    db.parent.mkdir(parents=True, exist_ok=True)
    os.environ["BASTION_DUCKDB_PATH"] = str(db)
    cli_args = [
        command,
        "--project-dir", str(paths.TRANSFORM_DIR),
        "--profiles-dir", str(paths.TRANSFORM_DIR),
        "--target", target,
        "--vars", f"{{raw_root: '{raw.as_posix()}'}}",
        *(extra or []),
    ]  # fmt: skip
    res = dbtRunner().invoke(cli_args)
    return bool(res.success)


def _cmd_build(args: argparse.Namespace) -> int:
    return 0 if run_dbt(args.target, extra=args.dbt_args) else 1


def _cmd_report(args: argparse.Namespace) -> int:
    from bastion.reports import alm, ccr, ews, market, svb

    if args.name == "alm":
        print("wrote", alm.build())
        return 0
    if args.name == "market":
        print("wrote", market.build())
    if args.name == "ccr":
        print("wrote", ccr.build())
        return 0
    note = ""
    if args.name in ("ews", "m7"):
        out, note = ews.build()
        print("wrote", out)
    if args.name in ("svb", "m7"):
        print("wrote", svb.build(ews_note=note))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="bastion")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="download public data into $BASTION_DATA/raw")
    pi.add_argument("--source", default="core", help="comma list of sources, or 'core'")
    pi.add_argument("--quarters", default="", help="report dates for fdic-quarter, YYYYMMDD,...")
    pi.add_argument("--pin", action="store_true", help="record checksums in ingest/pins.json")
    pi.add_argument(
        "--allow-drift", action="store_true", help="warn instead of failing on pin drift"
    )
    pi.set_defaults(func=_cmd_ingest)

    pf = sub.add_parser("fixtures", help="regenerate synthetic CI fixtures")
    pf.add_argument("--check", action="store_true", help="verify committed fixtures are current")
    pf.set_defaults(func=_cmd_fixtures)

    pb = sub.add_parser("build", help="dbt build the lakehouse")
    pb.add_argument("--target", choices=["ci", "dev"], default="dev")
    pb.add_argument("dbt_args", nargs=argparse.REMAINDER, help="extra args passed to dbt")
    pb.set_defaults(func=_cmd_build)

    pr = sub.add_parser("report", help="regenerate a results document under docs/results")
    pr.add_argument(
        "name",
        choices=["svb", "ews", "m7", "alm", "market", "ccr"],
        help="m7 = ews then svb (svb cites ews)",
    )
    pr.set_defaults(func=_cmd_report)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
