#!/usr/bin/env python3
"""Internal Linux helper; token output is for captured launcher pipes only."""

import argparse
import getpass
import json
from pathlib import Path
import sys
import warnings

from linux_config import load_settings, save_private_json
from linux_authorization import (
    ensure_authorization,
    read_token,
    save_authorization,
    authorization_state,
    parse_authorization_result,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--settings", type=Path, default=Path(__file__).with_name("settings.json")
    )
    parser.add_argument(
        "command",
        choices=("settings", "ensure", "status", "token", "save", "save-secret"),
    )
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        warnings.simplefilter("error", getpass.GetPassWarning)
        settings = load_settings(args.settings)
        if args.command == "settings":
            print(json.dumps(settings))
        elif args.command == "ensure":
            print(json.dumps(ensure_authorization(settings, force=args.force)))
        elif args.command == "status":
            print(json.dumps(authorization_state(settings)))
        elif args.command == "token":
            if sys.stdout.isatty():
                raise RuntimeError("Refusing to display authorization in a terminal")
            print(read_token(settings))
        elif args.command == "save":
            if not sys.stdin.isatty():
                raise RuntimeError("Use interactive hidden credential entry")
            access = getpass.getpass(
                "Official authorization result URL or access token (hidden): "
            )
            if access.startswith("https://"):
                access, refresh, expires = parse_authorization_result(access)
            else:
                refresh = getpass.getpass(
                    "Refresh token, or empty for experience route (hidden): "
                )
                expires = int(
                    input(
                        "Remaining validity in seconds (from authorization response): "
                    )
                )
            save_authorization(settings, access, refresh, expires, replace=args.replace)
            print("Authorization saved privately. Run the read-only MCP checks next.")
        else:
            if not sys.stdin.isatty() or not settings.get("appKey"):
                raise RuntimeError(
                    "Interactive entry and configured matching AppKey required"
                )
            secret = getpass.getpass("Application SecretKey (hidden): ")
            if not secret:
                raise RuntimeError("Empty application secret")
            save_private_json(
                Path(settings["secretFile"]),
                {
                    "format": "baidu-mcp-linux-secret-v1",
                    "app_key": settings["appKey"],
                    "secret_key": secret,
                },
                Path(settings["deploymentRoot"]),
                replace=args.replace,
            )
            print("Application secret saved privately.")
        return 0
    except Exception:
        print(
            "Baidu Linux authorization helper failed. Check private paths, permissions, settings and authorization.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
