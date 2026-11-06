"""Original-app OAuth code flow in a separate private Linux profile."""

from datetime import datetime, timezone
from pathlib import Path
import re
import urllib.parse

from linux_config import (
    private_path,
    read_private_json,
    save_private_json,
    fsync_directory,
)
from linux_authorization import expiry, refresh_lock, request_refresh


def _profile(settings):
    root = Path(settings["deploymentRoot"])
    if (
        settings.get("platform") != "linux"
        or settings.get("authorizationProfile") != "original-app"
        or not isinstance(settings.get("appKey"), str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", settings["appKey"])
        or Path(settings["tokenFile"]) != root / "original-app-authorization.json"
        or Path(settings["secretFile"]) != root / "original-app-secret.json"
    ):
        raise RuntimeError("Isolated original-app profile required")
    private_path(settings["tokenFile"], root)
    private_path(settings["secretFile"], root)
    default = read_private_json(root / "settings.json", root)
    if (
        default.get("tokenFile") == settings["tokenFile"]
        or default.get("secretFile") == settings["secretFile"]
    ):
        raise RuntimeError("Active default credentials must remain separate")
    return root


def prepare_app_profile(settings, app_key):
    root = Path(settings["deploymentRoot"])
    profile = {
        **settings,
        "authorizationProfile": "original-app",
        "appKey": app_key,
        "tokenFile": str(root / "original-app-authorization.json"),
        "secretFile": str(root / "original-app-secret.json"),
    }
    profile.pop("settingsFile", None)
    _profile(profile)
    path = root / "original-app-settings.json"
    if path.exists():
        if read_private_json(path, root) != profile:
            raise RuntimeError(
                "Existing original-app profile preserved; configuration differs"
            )
    else:
        save_private_json(path, profile, root, replace=False)
    return profile


def authorization_url(app_key, state):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", app_key) or not state:
        raise RuntimeError("Application identity and state required")
    return "https://openapi.baidu.com/oauth/2.0/authorize?" + urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": app_key,
            "redirect_uri": "oob",
            "scope": "basic,netdisk",
            "state": state,
        }
    )


def parse_authorization_code(value, state):
    try:
        if not isinstance(value, str) or not value or len(value) > 8192:
            raise ValueError()
        if value.startswith("https://"):
            url = urllib.parse.urlsplit(value)
            if (
                (url.scheme, url.hostname, url.path)
                != ("https", "openapi.baidu.com", "/oauth/2.0/login_success")
                or url.username
                or url.password
                or url.port
                or url.fragment
            ):
                raise ValueError()
            fields = {}
            for key, item in urllib.parse.parse_qsl(url.query, strict_parsing=True):
                if key in fields:
                    raise ValueError()
                fields[key] = item
            if fields.get("state") != state or "error" in fields:
                raise ValueError()
            value = fields["code"]
        if not re.fullmatch(r"[A-Za-z0-9._~-]{1,4096}", value):
            raise ValueError()
        return value
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("Invalid one-time code or authorization state") from None


def _validate_bundle(bundle, settings):
    if (
        not isinstance(bundle, dict)
        or set(bundle) != {"format", "app_key", "secret", "authorization"}
        or bundle["format"] != "baidu-mcp-linux-authorization-bundle-v1"
        or bundle["app_key"] != settings["appKey"]
    ):
        raise RuntimeError("Invalid pending authorization identity")
    secret, token = bundle["secret"], bundle["authorization"]
    if (
        secret.get("format") != "baidu-mcp-linux-secret-v1"
        or secret.get("app_key") != settings["appKey"]
        or token.get("format") != "baidu-mcp-linux-token-v1"
    ):
        raise RuntimeError("Invalid pending authorization format")
    for value in (
        secret.get("secret_key"),
        token.get("access_token"),
        token.get("refresh_token"),
    ):
        if not isinstance(value, str) or not value or any(c.isspace() for c in value):
            raise RuntimeError("Incomplete application credentials")
    result = expiry(token, datetime.now(timezone.utc))
    if result["status"] in ("unknown", "expired"):
        raise RuntimeError("Authorization expiry is invalid")
    return result


def _preflight(settings, root, replace):
    for key in ("tokenFile", "secretFile"):
        path = Path(settings[key])
        if path.exists():
            read_private_json(path, root)
            if not replace:
                raise RuntimeError(
                    "Existing original-app credentials preserved; explicit replacement required"
                )
    if Path(settings["tokenFile"] + ".pending-refresh").exists():
        raise RuntimeError("Resolve pending refresh before authorizing again")


def _publish(settings, bundle, root, *, replace):
    result = _validate_bundle(bundle, settings)
    save_private_json(
        Path(settings["secretFile"]), bundle["secret"], root, replace=replace
    )
    save_private_json(
        Path(settings["tokenFile"]), bundle["authorization"], root, replace=replace
    )
    pending = Path(settings["tokenFile"] + ".pending-authorization")
    pending.unlink()
    fsync_directory(root)
    return {**result, "hasRefreshToken": True, "action": "authorization_saved"}


def exchange_app_authorization(settings, secret, code, *, request=None, replace=False):
    try:
        root = _profile(settings)
        if (
            not isinstance(secret, str)
            or not secret
            or any(c.isspace() for c in secret)
        ):
            raise RuntimeError("Application secret required")
        code = parse_authorization_code(code, "local-oob-entry")
        with refresh_lock(settings):
            pending = Path(settings["tokenFile"] + ".pending-authorization")
            private_path(pending, root)
            if pending.exists() or pending.is_symlink():
                raise RuntimeError("Pending authorization recovery required")
            _preflight(settings, root, replace)
            response = (request or request_refresh)(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings["appKey"],
                    "client_secret": secret,
                    "redirect_uri": "oob",
                }
            )
            if not isinstance(response, dict) or "netdisk" not in re.split(
                r"[,\s]+", str(response.get("scope", ""))
            ):
                raise RuntimeError("Netdisk scope required")
            bundle = {
                "format": "baidu-mcp-linux-authorization-bundle-v1",
                "app_key": settings["appKey"],
                "secret": {
                    "format": "baidu-mcp-linux-secret-v1",
                    "app_key": settings["appKey"],
                    "secret_key": secret,
                },
                "authorization": {
                    "format": "baidu-mcp-linux-token-v1",
                    "access_token": response.get("access_token"),
                    "refresh_token": response.get("refresh_token"),
                    "expires_in": response.get("expires_in"),
                    "saved_at_utc": datetime.now(timezone.utc).isoformat(),
                },
            }
            _validate_bundle(bundle, settings)
            save_private_json(pending, bundle, root, replace=False)
            return _publish(settings, bundle, root, replace=replace)
    except Exception:
        raise RuntimeError(
            "Application authorization failed; no automatic retry. Inspect private profile and pending recovery, then verify application/code."
        ) from None


def recover_app_authorization(settings, *, replace=False):
    try:
        root = _profile(settings)
        with refresh_lock(settings):
            pending = Path(settings["tokenFile"] + ".pending-authorization")
            bundle = read_private_json(pending, root)
            _preflight(settings, root, replace)
            return _publish(settings, bundle, root, replace=replace)
    except Exception:
        raise RuntimeError(
            "Application authorization recovery failed; pending material retained where present"
        ) from None
