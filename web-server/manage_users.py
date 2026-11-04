#!/usr/bin/env python3
"""Manage local deployment-manager accounts without storing plaintext passwords."""

import argparse
import getpass
import json
import re
import sys
import tempfile
from pathlib import Path

from auth import make_password_record

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def load_config(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as config_file:
            return json.load(config_file)
    except FileNotFoundError:
        raise SystemExit(f"Config file not found: {path}")
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid JSON in {path}: {error}")


def save_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temp_file:
        json.dump(config, temp_file, indent=2)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)
    temp_path.chmod(0o600)
    temp_path.replace(path)
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    actions = parser.add_subparsers(dest="action", required=True)
    add_parser = actions.add_parser("add", help="add or replace a user")
    add_parser.add_argument("email")
    remove_parser = actions.add_parser("remove", help="remove a user")
    remove_parser.add_argument("email")
    actions.add_parser("list", help="list configured email addresses")
    args = parser.parse_args()

    email = getattr(args, "email", "").strip().casefold()
    if args.action != "list" and not EMAIL_PATTERN.fullmatch(email):
        parser.error("enter a valid email address")

    config = load_config(args.config)
    users = config.setdefault("users", [])

    if args.action == "list":
        if users:
            for user in users:
                print(user["email"])
        else:
            print("No users configured")
        return 0

    if args.action == "remove":
        updated_users = [user for user in users if user.get("email", "").casefold() != email]
        if len(updated_users) == len(users):
            print(f"User not found: {email}", file=sys.stderr)
            return 1
        config["users"] = updated_users
        save_config(args.config, config)
        print(f"Removed user: {email}")
        return 0

    password = getpass.getpass("New password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(password) < 12:
        parser.error("password must contain at least 12 characters")
    if password != confirmation:
        parser.error("passwords do not match")

    record = make_password_record(email, password)
    config["users"] = [user for user in users if user.get("email", "").casefold() != email]
    config["users"].append(record)
    save_config(args.config, config)
    print(f"Added user: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
