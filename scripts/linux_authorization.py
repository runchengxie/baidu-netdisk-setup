"""Headless Linux OAuth files: strict expiry, serialized refresh, no secret logs."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

from linux_config import (
    private_path,
    read_private_json,
    save_private_json,
    fsync_directory,
)


def utcnow():
    return datetime.now(timezone.utc)


def expiry(saved, now):
    try:
        lifetime = saved["expires_in"]
        if type(lifetime) is not int or not 0 < lifetime <= 31536000:
            raise ValueError()
        created = datetime.fromisoformat(saved["saved_at_utc"])
        if created.tzinfo is None or created.utcoffset() is None or now.tzinfo is None:
            raise ValueError()
        remaining = lifetime - (now - created).total_seconds()
        if (created - now).total_seconds() > 5:
            raise ValueError()
        return {
            "status": "expired"
            if remaining <= 0
            else "expiring"
            if remaining <= 604800
            else "valid",
            "remainingSeconds": remaining,
            "revision": hashlib.sha256(
                json.dumps(saved, sort_keys=True).encode()
            ).hexdigest(),
            "expiresAtUtc": datetime.fromtimestamp(
                created.timestamp() + lifetime, timezone.utc
            ).isoformat(),
        }
    except (ValueError, TypeError, KeyError, OverflowError):
        return {"status": "unknown", "remainingSeconds": 0, "revision": "unknown"}


def _saved(settings):
    value = read_private_json(
        Path(settings["tokenFile"]), Path(settings["deploymentRoot"])
    )
    if not isinstance(value, dict) or value.get("format") != "baidu-mcp-linux-token-v1":
        raise RuntimeError(
            "Linux authorization format required; Windows DPAPI files cannot be reused"
        )
    token = value.get("access_token")
    if (
        not isinstance(token, str)
        or not token
        or token.strip() != token
        or any(c.isspace() for c in token)
    ):
        raise RuntimeError("Invalid authorization")
    return value


def read_token(settings, *, now=None):
    saved = _saved(settings)
    if expiry(saved, now or utcnow())["status"] in ("unknown", "expired"):
        raise RuntimeError("Authorization expired or unavailable; reauthorize")
    return saved["access_token"]


def authorization_state(settings, *, now=None):
    return expiry(_saved(settings), now or utcnow())


def save_authorization(settings, access, refresh, expires, *, now=None, replace=False):
    now = now or utcnow()
    value = {
        "format": "baidu-mcp-linux-token-v1",
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": expires,
        "saved_at_utc": now.isoformat(),
    }
    if (
        not isinstance(access, str)
        or not access
        or any(c.isspace() for c in access)
        or not isinstance(refresh, str)
    ):
        raise RuntimeError("Invalid authorization")
    if expiry(value, now)["status"] in ("unknown", "expired"):
        raise RuntimeError("Invalid authorization expiry")
    with refresh_lock(settings):
        save_private_json(
            Path(settings["tokenFile"]),
            value,
            Path(settings["deploymentRoot"]),
            replace=replace,
        )


@contextmanager
def refresh_lock(settings, *, timeout=45):
    import fcntl
    root = Path(settings["deploymentRoot"])
    path = private_path(Path(settings["tokenFile"] + ".refresh.lock"), root)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise RuntimeError("Unsafe refresh lock permissions")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Authorization refresh lock timed out")
                time.sleep(0.1)
        yield
    finally:
        os.close(fd)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_refresh(fields):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    request = urllib.request.Request(
        "https://openapi.baidu.com/oauth/2.0/token",
        data=urllib.parse.urlencode(fields).encode(),
        method="POST",
    )
    with opener.open(request, timeout=30) as response:
        return json.load(response)


def ensure_authorization(settings, *, now=None, force=False, request=None):
    now = now or utcnow()
    saved = _saved(settings)
    result = expiry(saved, now)
    result["refreshAction"] = "not_due"
    if result["status"] == "unknown":
        return result
    if result["remainingSeconds"] > 604800 and not force:
        return result
    root = Path(settings["deploymentRoot"])
    try:
        secret = read_private_json(Path(settings["secretFile"]), root)
        if (
            secret.get("format") != "baidu-mcp-linux-secret-v1"
            or not settings.get("appKey")
            or secret.get("app_key") != settings["appKey"]
            or not secret.get("secret_key")
            or not saved.get("refresh_token")
        ):
            raise RuntimeError("Missing refresh materials")
    except (OSError, RuntimeError, ValueError, AttributeError):
        result.update(
            refreshAction="unavailable", refreshFailure="refresh_materials_unavailable"
        )
        return result
    with refresh_lock(settings):
        latest = _saved(settings)
        if latest["saved_at_utc"] != saved["saved_at_utc"]:
            return {**expiry(latest, now), "refreshAction": "updated_by_peer"}
        pending = Path(settings["tokenFile"] + ".pending-refresh")
        if pending.exists():
            return {
                **result,
                "refreshAction": "failed",
                "refreshFailure": "pending_credentials_recovery_required",
            }
        try:
            response = (request or request_refresh)(
                {
                    "grant_type": "refresh_token",
                    "client_id": settings["appKey"],
                    "client_secret": secret["secret_key"],
                    "refresh_token": latest["refresh_token"],
                }
            )
            access, refresh, lifetime = (
                response["access_token"],
                response["refresh_token"],
                response["expires_in"],
            )
            candidate = {
                "format": "baidu-mcp-linux-token-v1",
                "access_token": access,
                "refresh_token": refresh,
                "expires_in": lifetime,
                "saved_at_utc": now.isoformat(),
            }
            if (
                not isinstance(access, str)
                or not access
                or any(c.isspace() for c in access)
                or not isinstance(refresh, str)
                or not refresh
                or expiry(candidate, now)["status"] in ("unknown", "expired")
            ):
                raise RuntimeError("Invalid refresh response")
            save_private_json(pending, candidate, root, replace=False)
            if _saved(settings) != latest:
                raise RuntimeError(
                    "Authorization changed during refresh; pending recovery retained"
                )
            os.replace(pending, Path(settings["tokenFile"]))
            fsync_directory(root)
            return {**expiry(candidate, now), "refreshAction": "refreshed"}
        except Exception:
            return {
                **result,
                "refreshAction": "failed",
                "refreshFailure": "oauth_or_persistence_failed",
            }


def parse_authorization_result(url):
    """Accept only a fresh official OAuth result, never arbitrary redirect hosts."""
    try:
        parsed = urllib.parse.urlsplit(url)
        if (
            (parsed.scheme, parsed.hostname, parsed.path)
            != ("https", "openapi.baidu.com", "/oauth/2.0/login_success")
            or parsed.username
            or parsed.password
            or parsed.port
        ):
            raise ValueError()
        pairs = urllib.parse.parse_qsl(parsed.fragment, strict_parsing=True)
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError()
            values[key] = value
        access = values["access_token"]
        expires = int(values["expires_in"])
        if (
            not access
            or any(c.isspace() for c in access)
            or not 0 < expires <= 31536000
        ):
            raise ValueError()
        return access, values.get("refresh_token", ""), expires
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("Invalid official authorization result") from None
