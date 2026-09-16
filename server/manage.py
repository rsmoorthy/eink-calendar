#!/usr/bin/env python3
"""Administrative command line for the calendar server.

Usage:
  python manage.py create-admin <username>     set or reset an admin password
  python manage.py list-admins
  python manage.py delete-admin <username>
  python manage.py refresh [--days N] [--start YYYY-MM-DD]
  python manage.py generate [--days N] [--start YYYY-MM-DD] [--no-refresh]
  python manage.py seed-tamil-months
  python manage.py status
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import date as Date
from datetime import timedelta

from werkzeug.security import generate_password_hash

from assets_store import prepare_assets_dir
from calendar_config import ConfigStore
from calendar_db import Database
from calendar_service import CalendarService
from panchanga import TAMIL_MONTH_STARTS, today_ist


def cmd_create_admin(args) -> int:
    db = Database()
    password = args.password
    if not password:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.", file=sys.stderr)
            return 1
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1

    db.create_admin(args.username, generate_password_hash(password))
    print(f"Admin '{args.username}' saved.")
    return 0


def cmd_list_admins(_args) -> int:
    db = Database()
    rows = db.connection.execute(
        "SELECT username, created_at FROM admin_user ORDER BY username"
    ).fetchall()
    if not rows:
        print("No admin users. Create one with: python manage.py create-admin <name>")
        return 0
    for row in rows:
        print(f"{row['username']}  (created {row['created_at']})")
    return 0


def cmd_delete_admin(args) -> int:
    db = Database()
    with db.write() as conn:
        conn.execute("DELETE FROM admin_user WHERE username = ?", (args.username,))
    print(f"Admin '{args.username}' deleted.")
    return 0


def _service() -> CalendarService:
    # Seed the writable assets directory the same way the web app does, so a
    # CLI render sees the same artwork as a request-triggered one.
    return CalendarService(
        Database(), ConfigStore(), assets_dir=prepare_assets_dir()
    )


def cmd_refresh(args) -> int:
    service = _service()
    start = Date.fromisoformat(args.start) if args.start else today_ist()
    results = service.refresh_range(start, args.days)
    ok = sum(1 for value in results.values() if value)
    print(f"Refreshed {len(results)} days: {ok} ok, {len(results) - ok} failed.")
    for day, success in results.items():
        if not success:
            print(f"  failed: {day}")
    return 0 if ok else 1


def cmd_generate(args) -> int:
    service = _service()
    start = Date.fromisoformat(args.start) if args.start else today_ist()
    summary = service.generate_range(start, args.days, refresh=not args.no_refresh)
    print(
        f"Generated {summary['generated']}/{summary['days']} images "
        f"from {summary['start']}."
    )
    for failure in summary["failed"]:
        print(f"  failed: {failure}")
    return 0 if summary["generated"] == summary["days"] else 1


def cmd_seed_tamil_months(_args) -> int:
    db = Database()
    db.seed_tamil_months(TAMIL_MONTH_STARTS)
    print(f"Seeded {len(TAMIL_MONTH_STARTS)} Tamil month start dates.")
    return 0


def cmd_status(_args) -> int:
    db = Database()
    today = today_ist()
    total = db.connection.execute("SELECT COUNT(*) AS n FROM day").fetchone()["n"]
    with_bitmap = db.connection.execute(
        "SELECT COUNT(*) AS n FROM day WHERE bitmap IS NOT NULL"
    ).fetchone()["n"]
    failed = db.connection.execute(
        "SELECT COUNT(*) AS n FROM day WHERE panchanga_ok = 0"
    ).fetchone()["n"]
    today_row = db.get_day(today)

    print(f"Database      : {db.path}")
    print(f"Days stored   : {total}")
    print(f"With bitmap   : {with_bitmap}")
    print(f"Scrape failed : {failed}")
    print(f"Admins        : {db.admin_count()}")
    if today_row is None:
        print(f"Today ({today}): no record")
    else:
        print(
            f"Today ({today}): checksum={today_row['checksum']} "
            f"panchanga_ok={bool(today_row['panchanga_ok'])}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-admin", help="create or update an admin user")
    create.add_argument("username")
    create.add_argument("--password", help="skip the interactive prompt")
    create.set_defaults(func=cmd_create_admin)

    listing = sub.add_parser("list-admins", help="list admin users")
    listing.set_defaults(func=cmd_list_admins)

    delete = sub.add_parser("delete-admin", help="delete an admin user")
    delete.add_argument("username")
    delete.set_defaults(func=cmd_delete_admin)

    refresh = sub.add_parser("refresh", help="scrape panchanga for a date range")
    refresh.add_argument("--days", type=int, default=4)
    refresh.add_argument("--start", help="YYYY-MM-DD, defaults to today IST")
    refresh.set_defaults(func=cmd_refresh)

    generate = sub.add_parser("generate", help="render bitmaps for a date range")
    generate.add_argument("--days", type=int, default=90)
    generate.add_argument("--start", help="YYYY-MM-DD, defaults to today IST")
    generate.add_argument(
        "--no-refresh",
        action="store_true",
        help="skip the panchanga fetch and only re-render stored data",
    )
    generate.set_defaults(func=cmd_generate)

    seed = sub.add_parser("seed-tamil-months", help="load the built-in Tamil month table")
    seed.set_defaults(func=cmd_seed_tamil_months)

    status = sub.add_parser("status", help="show a summary of stored state")
    status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
