from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from linux_config import read_private_json, save_private_json
from linux_app_authorization import (
    prepare_app_profile,
    authorization_url,
    parse_authorization_code,
    exchange_app_authorization,
    recover_app_authorization,
)
from linux_authorization import read_token, ensure_authorization


@unittest.skipUnless(sys.platform == "linux", "Linux backend tests")
class OriginalAppAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.default = {
            "platform": "linux",
            "installation": "baidu-netdisk-linux-v1",
            "deploymentRoot": str(self.root),
            "tokenFile": str(self.root / "authorization.json"),
            "secretFile": str(self.root / "app-secret.json"),
            "appKey": "",
            "python": sys.executable,
            "bridge": "/fixture/bridge.js",
            "officialDir": "/fixture/official",
        }
        save_private_json(self.root / "settings.json", self.default, self.root)
        save_private_json(
            self.root / "authorization.json", {"unchanged": "experience"}, self.root
        )
        self.profile = prepare_app_profile(self.default, "example-owned-app")

    def request(self, fields):
        self.assertEqual(
            fields,
            {
                "grant_type": "authorization_code",
                "code": "synthetic-code",
                "client_id": "example-owned-app",
                "client_secret": "synthetic-secret",
                "redirect_uri": "oob",
            },
        )
        return {
            "access_token": "synthetic-app-access",
            "refresh_token": "synthetic-app-refresh",
            "expires_in": 2592000,
            "scope": "basic netdisk",
        }

    def test_profile_is_separate_idempotent_and_does_not_modify_default(self):
        self.assertEqual(
            Path(self.profile["tokenFile"]).name, "original-app-authorization.json"
        )
        self.assertEqual(
            prepare_app_profile(self.default, "example-owned-app"), self.profile
        )
        with self.assertRaises(RuntimeError):
            prepare_app_profile(self.default, "another-app")
        self.assertEqual(
            read_private_json(self.root / "settings.json", self.root), self.default
        )
        self.assertEqual(
            read_private_json(self.root / "authorization.json", self.root),
            {"unchanged": "experience"},
        )

    def test_authorization_url_uses_code_oob_scope_and_state(self):
        parsed = urlsplit(authorization_url("example-owned-app", "state-123"))
        self.assertEqual(parsed.netloc, "openapi.baidu.com")
        self.assertEqual(
            parse_qs(parsed.query),
            {
                "response_type": ["code"],
                "client_id": ["example-owned-app"],
                "redirect_uri": ["oob"],
                "scope": ["basic,netdisk"],
                "state": ["state-123"],
            },
        )
        self.assertEqual(
            parse_authorization_code("synthetic-code", "state-123"), "synthetic-code"
        )
        self.assertEqual(
            parse_authorization_code(
                "https://openapi.baidu.com/oauth/2.0/login_success?code=synthetic-code&state=state-123",
                "state-123",
            ),
            "synthetic-code",
        )
        for value in (
            "https://example.invalid/?code=synthetic-code&state=state-123",
            "https://openapi.baidu.com/oauth/2.0/login_success?code=a&state=wrong",
            "https://openapi.baidu.com/oauth/2.0/login_success?code=a&code=b&state=state-123",
            "code with whitespace",
        ):
            with self.assertRaises(RuntimeError):
                parse_authorization_code(value, "state-123")

    def test_exchange_stores_refresh_materials_privately_without_default_change(self):
        state = exchange_app_authorization(
            self.profile, "synthetic-secret", "synthetic-code", request=self.request
        )
        self.assertTrue(state["hasRefreshToken"])
        self.assertEqual(state["status"], "valid")
        self.assertNotIn("synthetic", json.dumps(state))
        self.assertEqual(read_token(self.profile), "synthetic-app-access")
        secret = Path(self.profile["secretFile"])
        self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            read_private_json(secret, self.root)["app_key"], "example-owned-app"
        )
        self.assertEqual(
            read_private_json(self.root / "authorization.json", self.root),
            {"unchanged": "experience"},
        )
        with self.assertRaises(RuntimeError):
            exchange_app_authorization(
                self.profile,
                "synthetic-secret",
                "synthetic-code",
                request=lambda f: self.fail("Must not exchange twice"),
            )

    def test_missing_refresh_or_scope_never_publishes_files(self):
        for missing in ("refresh_token", "scope"):

            def request(fields):
                result = self.request(fields)
                result.pop(missing)
                return result

            with self.assertRaises(RuntimeError):
                exchange_app_authorization(
                    self.profile, "synthetic-secret", "synthetic-code", request=request
                )
            self.assertFalse(Path(self.profile["tokenFile"]).exists())
            self.assertFalse(Path(self.profile["secretFile"]).exists())

    def test_exchange_failure_is_once_only_and_diagnostics_are_sanitized(self):
        calls = []

        def request(fields):
            calls.append(fields)
            raise OSError("client_secret=synthetic-secret code=synthetic-code")

        with self.assertRaises(RuntimeError) as caught:
            exchange_app_authorization(
                self.profile, "synthetic-secret", "synthetic-code", request=request
            )
        self.assertEqual(len(calls), 1)
        self.assertNotIn("synthetic", str(caught.exception))

    def test_partial_publication_keeps_complete_bundle_and_can_recover_without_network(
        self,
    ):
        import linux_app_authorization as module

        original = module.save_private_json

        def fail_token(path, *args, **kwargs):
            if Path(path) == Path(self.profile["tokenFile"]):
                raise OSError("synthetic failure")
            return original(path, *args, **kwargs)

        with patch.object(module, "save_private_json", side_effect=fail_token):
            with self.assertRaises(RuntimeError):
                exchange_app_authorization(
                    self.profile,
                    "synthetic-secret",
                    "synthetic-code",
                    request=self.request,
                )
        pending = Path(self.profile["tokenFile"] + ".pending-authorization")
        self.assertTrue(pending.is_file())
        bundle = read_private_json(pending, self.root)
        self.assertEqual(bundle["secret"]["secret_key"], "synthetic-secret")
        self.assertEqual(
            bundle["authorization"]["refresh_token"], "synthetic-app-refresh"
        )
        with self.assertRaises(RuntimeError):
            exchange_app_authorization(
                self.profile,
                "synthetic-secret",
                "synthetic-code",
                request=lambda f: self.fail("No repeat while pending"),
            )
        with self.assertRaises(RuntimeError):
            recover_app_authorization(self.profile)
        state = recover_app_authorization(self.profile, replace=True)
        self.assertEqual(state["status"], "valid")
        self.assertFalse(pending.exists())
        self.assertEqual(read_token(self.profile), "synthetic-app-access")

    def test_active_experience_profile_cannot_be_used_for_code_exchange(self):
        with self.assertRaises(RuntimeError):
            exchange_app_authorization(
                self.default,
                "synthetic-secret",
                "synthetic-code",
                request=lambda f: self.fail("Default must not exchange"),
            )

    def test_manual_secret_save_waits_for_authorization_publication_lock(self):
        import importlib.util
        import concurrent.futures
        import threading
        import linux_app_authorization as module

        loader = importlib.util.spec_from_file_location(
            "credential_app_helper",
            Path(__file__).resolve().parents[1] / "scripts" / "credential-helper.py",
        )
        helper = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(helper)
        original = module.save_private_json
        published = threading.Event()
        release = threading.Event()

        def paused_save(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if Path(path) == Path(self.profile["secretFile"]):
                published.set()
                release.wait(3)
            return result

        with (
            concurrent.futures.ThreadPoolExecutor(2) as pool,
            patch.object(module, "save_private_json", side_effect=paused_save),
            patch.object(helper.sys.stdin, "isatty", return_value=True),
            patch.object(helper.getpass, "getpass", return_value="replacement-secret"),
        ):
            exchange = pool.submit(
                exchange_app_authorization,
                self.profile,
                "synthetic-secret",
                "synthetic-code",
                request=self.request,
            )
            self.assertTrue(published.wait(2))
            manual = pool.submit(
                helper.main,
                [
                    "--settings",
                    str(self.root / "original-app-settings.json"),
                    "save-secret",
                    "--replace",
                ],
            )
            try:
                with self.assertRaises(concurrent.futures.TimeoutError):
                    manual.result(timeout=0.1)
            finally:
                release.set()
            self.assertEqual(exchange.result()["status"], "valid")
            self.assertEqual(manual.result(), 0)

    def test_manual_token_save_cannot_bypass_pending_authorization(self):
        from linux_authorization import save_authorization

        pending = Path(self.profile["tokenFile"] + ".pending-authorization")
        save_private_json(pending, {"retained": "pending"}, self.root)
        with self.assertRaises(RuntimeError):
            save_authorization(
                self.profile, "manual-access", "manual-refresh", 2592000, replace=True
            )
        self.assertFalse(Path(self.profile["tokenFile"]).exists())

    def test_refresh_reads_secret_after_acquiring_shared_lock(self):
        import concurrent.futures
        import threading
        from contextlib import contextmanager
        import linux_authorization as auth

        exchange_app_authorization(
            self.profile, "synthetic-secret", "synthetic-code", request=self.request
        )
        original_lock = auth.refresh_lock
        entered = threading.Event()
        used = []

        @contextmanager
        def observed_lock(settings):
            entered.set()
            with original_lock(settings):
                yield

        def request(fields):
            used.append(fields["client_secret"])
            return {
                "access_token": "refreshed-access",
                "refresh_token": "refreshed-refresh",
                "expires_in": 2592000,
            }

        with (
            concurrent.futures.ThreadPoolExecutor(1) as pool,
            patch.object(auth, "refresh_lock", observed_lock),
        ):
            with original_lock(self.profile):
                future = pool.submit(
                    ensure_authorization, self.profile, force=True, request=request
                )
                self.assertTrue(entered.wait(2))
                secret = read_private_json(Path(self.profile["secretFile"]), self.root)
                secret["secret_key"] = "new-secret-under-lock"
                save_private_json(Path(self.profile["secretFile"]), secret, self.root)
            self.assertEqual(future.result()["refreshAction"], "refreshed")
        self.assertEqual(used, ["new-secret-under-lock"])

    def test_manual_secret_save_refuses_both_pending_recovery_states(self):
        from linux_authorization import save_application_secret

        for suffix in (".pending-authorization", ".pending-refresh"):
            pending = Path(self.profile["tokenFile"] + suffix)
            save_private_json(pending, {"retained": "pending"}, self.root)
            with self.assertRaises(RuntimeError):
                save_application_secret(self.profile, "manual-secret", replace=True)
            self.assertFalse(Path(self.profile["secretFile"]).exists())
            pending.unlink()
