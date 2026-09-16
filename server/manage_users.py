#!/usr/bin/env python3
import sys
import argparse
import os

# Add server directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import init_db, create_or_update_user, get_user_by_username


def main():
    parser = argparse.ArgumentParser(description="Manage Admin Users for Calendar Server")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-user", help="Create or reset user password")
    create_parser.add_argument("--username", "-u", required=True, help="Username")
    create_parser.add_argument("--password", "-p", required=True, help="Password")

    check_parser = subparsers.add_parser("check-user", help="Check if user exists")
    check_parser.add_argument("--username", "-u", required=True, help="Username")

    args = parser.parse_args()
    init_db()

    if args.command == "create-user":
        create_or_update_user(args.username, args.password)
        print(f"User '{args.username}' created/updated successfully.")
    elif args.command == "check-user":
        u = get_user_by_username(args.username)
        if u:
            print(f"User '{args.username}' found (created at {u['created_at']}).")
        else:
            print(f"User '{args.username}' does not exist.")


if __name__ == "__main__":
    main()
