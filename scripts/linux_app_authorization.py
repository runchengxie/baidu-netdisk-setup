"""Original-app OAuth code flow in a separate private Linux profile."""

from datetime import datetime, timezone
from pathlib import Path
import re
import json
import urllib.error
import urllib.parse

from linux_config import (
    private_path,
    read_private_json,
    save_private_json,
    fsync_directory,
)
from linux_authorization import expiry, refresh_lock, request_refresh


_ERROR_MESSAGES = {
    "invalid_code": "The code is empty or has an invalid format. Copy the fresh code shown on the OOB page.",
    "unexpected_result_url": "The result URL is not the supported official callback. Copy the displayed OOB code instead.",
    "authorization_state_missing": "The result URL has no state. Copy the displayed OOB code instead.",
    "authorization_state_mismatch": "The result belongs to another authorization request. Use the current run and its new link.",
    "secret_required": "Enter the original application SecretKey without surrounding whitespace.",
    "invalid_client": "Baidu rejected the application credentials. Check that SecretKey belongs to the configured AppKey.",
    "invalid_grant": "Baidu rejected the one-time code. It may be expired, used, or from another application. Obtain a new code.",
    "access_denied": "Authorization was denied. Confirm the application and requested permissions in the browser.",
    "invalid_scope": "Baidu rejected the requested permissions. Check the application Netdisk access.",
    "unsupported_grant_type": "Baidu rejected the authorization-code grant. Check the application OAuth configuration.",
    "oauth_rejected": "Baidu rejected the exchange. No server description or credential is displayed.",
    "network_failure": "The OAuth request failed at the network or TLS layer. No automatic code retry was made.",
    "refresh_token_missing": "The response has no refresh token; no candidate credentials were saved.",
    "netdisk_scope_missing": "The response does not grant Netdisk scope; no candidate credentials were saved.",
    "invalid_response": "The OAuth response is incomplete or invalid; no candidate credentials were published.",
    "existing_credentials": "Candidate credentials already exist. Inspect them before intentional replacement.",
    "pending_recovery_required": "Pending credentials are retained. Recover them before another exchange.",
    "local_configuration_error": "Private profile, ownership or permissions validation failed before exchange.",
    "storage_failure": "Private credential publication failed. Preserve any pending authorization bundle and recover it.",
    "recovery_failure": "Private authorization recovery failed. Existing pending material is retained.",
}


class AuthorizationFailure(RuntimeError):
    def __init__(self, code, phase):
        self.code = (
            code
            if isinstance(code, str) and code in _ERROR_MESSAGES
            else "oauth_rejected"
        )
        self.phase = (
            phase
            if phase
            in (
                "input",
                "preflight",
                "exchange",
                "validation",
                "publication",
                "recovery",
            )
            else "preflight"
        )
        super().__init__(_ERROR_MESSAGES[self.code])


def _oauth_failure(response):
    code = response.get("error") if isinstance(response, dict) else None
    allowed = (
        "invalid_client",
        "invalid_grant",
        "access_denied",
        "invalid_scope",
        "unsupported_grant_type",
    )
    return AuthorizationFailure(
        code if isinstance(code, str) and code in allowed else "oauth_rejected",
        "exchange",
    )


def _http_failure(error):
    try:
        response = json.loads(error.read(16384))
    except Exception:
        response = {}
    finally:
        error.close()
    return _oauth_failure(response)


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
        if not isinstance(value, str):
            raise ValueError()
        value = value.strip()
        if not value or len(value) > 8192:
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
                raise AuthorizationFailure("unexpected_result_url", "input")
            fields = {}
            for key, item in urllib.parse.parse_qsl(url.query, strict_parsing=True):
                if key in fields:
                    raise ValueError()
                fields[key] = item
            if not fields.get("state"):
                raise AuthorizationFailure("authorization_state_missing", "input")
            if fields["state"] != state:
                raise AuthorizationFailure("authorization_state_mismatch", "input")
            if "error" in fields:
                raise AuthorizationFailure("access_denied", "input")
            value = fields["code"]
        # OAuth codes are opaque; form encoding handles +, / and = safely.
        if (
            not 1 <= len(value) <= 4096
            or "://" in value
            or any(not 0x21 <= ord(c) <= 0x7E for c in value)
        ):
            raise ValueError()
        return value
    except AuthorizationFailure:
        raise
    except (ValueError, KeyError, TypeError):
        raise AuthorizationFailure("invalid_code", "input") from None


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
                raise AuthorizationFailure("existing_credentials", "preflight")
    if Path(settings["tokenFile"] + ".pending-refresh").exists():
        raise AuthorizationFailure("pending_recovery_required", "preflight")


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
    phase = "preflight"
    try:
        root = _profile(settings)
        if (
            not isinstance(secret, str)
            or not secret
            or any(c.isspace() for c in secret)
        ):
            raise AuthorizationFailure("secret_required", "preflight")
        code = parse_authorization_code(code, "local-oob-entry")
        with refresh_lock(settings):
            pending = Path(settings["tokenFile"] + ".pending-authorization")
            private_path(pending, root)
            if pending.exists() or pending.is_symlink():
                raise AuthorizationFailure("pending_recovery_required", "preflight")
            _preflight(settings, root, replace)
            phase = "exchange"
            response = (request or request_refresh)(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings["appKey"],
                    "client_secret": secret,
                    "redirect_uri": "oob",
                }
            )
            if isinstance(response, dict) and response.get("error"):
                raise _oauth_failure(response)
            phase = "validation"
            if not isinstance(response, dict):
                raise AuthorizationFailure("invalid_response", phase)
            if not response.get("refresh_token"):
                raise AuthorizationFailure("refresh_token_missing", phase)
            if "netdisk" not in re.split(r"[,\s]+", str(response.get("scope", ""))):
                raise AuthorizationFailure("netdisk_scope_missing", phase)
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
            phase = "publication"
            save_private_json(pending, bundle, root, replace=False)
            return _publish(settings, bundle, root, replace=replace)
    except AuthorizationFailure:
        raise
    except urllib.error.HTTPError as error:
        raise _http_failure(error) from None
    except OSError:
        code = (
            "network_failure"
            if phase == "exchange"
            else "storage_failure"
            if phase == "publication"
            else "local_configuration_error"
        )
        raise AuthorizationFailure(code, phase) from None
    except Exception:
        code = (
            "invalid_response"
            if phase in ("exchange", "validation")
            else "storage_failure"
            if phase == "publication"
            else "local_configuration_error"
        )
        raise AuthorizationFailure(code, phase) from None


def recover_app_authorization(settings, *, replace=False):
    try:
        root = _profile(settings)
        with refresh_lock(settings):
            pending = Path(settings["tokenFile"] + ".pending-authorization")
            bundle = read_private_json(pending, root)
            _preflight(settings, root, replace)
            return _publish(settings, bundle, root, replace=replace)
    except AuthorizationFailure:
        raise
    except Exception:
        raise AuthorizationFailure("recovery_failure", "recovery") from None
