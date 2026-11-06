#!/usr/bin/env python3
"""Internal Linux helper; token output is for captured launcher pipes only."""

import argparse
import getpass
import json
from pathlib import Path
import sys
import warnings
import secrets

from linux_config import load_settings
from linux_app_authorization import AuthorizationFailure
from linux_authorization import (
    ensure_authorization,
    read_token,
    save_authorization,
    authorization_state,
    parse_authorization_result,
    save_application_secret,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--settings", type=Path, default=Path(__file__).with_name("settings.json")
    )
    parser.add_argument(
        "command",
        choices=(
            "settings",
            "ensure",
            "status",
            "token",
            "save",
            "save-secret",
            "prepare-app",
            "authorize-app",
            "recover-app",
        ),
    )
    parser.add_argument(
        "--app-key", help="Non-secret original application AppKey; prepare-app only"
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
        elif args.command in ("prepare-app", "authorize-app", "recover-app"):
            from linux_app_authorization import (
                prepare_app_profile,
                authorization_url,
                parse_authorization_code,
                exchange_app_authorization,
                recover_app_authorization,
            )

            if args.command == "prepare-app":
                prepare_app_profile(settings, args.app_key)
                print(
                    json.dumps(
                        {
                            "status": "profile_prepared",
                            "settingsFile": str(
                                Path(settings["deploymentRoot"])
                                / "original-app-settings.json"
                            ),
                            "defaultChanged": False,
                        }
                    )
                )
            elif args.command == "recover-app":
                print(
                    json.dumps(
                        recover_app_authorization(settings, replace=args.replace)
                    )
                )
            else:
                if not sys.stdin.isatty():
                    raise RuntimeError(
                        "Use interactive hidden application authorization"
                    )
                secret = getpass.getpass("Original application SecretKey (hidden): ")
                state = secrets.token_urlsafe(32)
                print(
                    "Open this official URL in your browser, confirm the original application and permissions:"
                )
                print(authorization_url(settings["appKey"], state))
                code = getpass.getpass(
                    "Fresh code from the OOB page, or complete official result URL (hidden): "
                )
                code = parse_authorization_code(code, state)
                print(
                    json.dumps(
                        exchange_app_authorization(
                            settings, secret, code, replace=args.replace
                        )
                    )
                )
        else:
            if not sys.stdin.isatty() or not settings.get("appKey"):
                raise RuntimeError(
                    "Interactive entry and configured matching AppKey required"
                )
            secret = getpass.getpass("Application SecretKey (hidden): ")
            if not secret:
                raise RuntimeError("Empty application secret")
            save_application_secret(settings, secret, replace=args.replace)
            print("Application secret saved privately.")
        return 0
    except AuthorizationFailure as failure:
        print(
            f"Baidu application authorization failed [{failure.phase}/{failure.code}]: {failure}",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            "Baidu Linux authorization helper failed. Check private paths, permissions, settings and authorization.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
