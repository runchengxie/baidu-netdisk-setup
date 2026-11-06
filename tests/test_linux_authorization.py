import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from linux_config import (
    load_settings,
    read_private_json,
    save_private_json,
    resolve_roots,
)
from linux_authorization import ensure_authorization, read_token, save_authorization

NOW = datetime(2026, 11, 6, 15, tzinfo=timezone.utc)


@unittest.skipUnless(sys.platform == 'linux', 'Linux backend tests')
class LinuxAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.settings = {
            "platform": "linux",
            "deploymentRoot": str(self.root),
            "tokenFile": str(self.root / "token.json"),
            "secretFile": str(self.root / "secret.json"),
            "appKey": "example",
        }

    def save(self, now=NOW, expires=30 * 86400):
        save_authorization(
            self.settings, "artificial-access", "artificial-refresh", expires, now=now
        )

    def test_private_atomic_save_and_valid_token_read(self):
        self.save()
        path = Path(self.settings["tokenFile"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(read_token(self.settings, now=NOW), "artificial-access")
        self.assertEqual(
            ensure_authorization(self.settings, now=NOW)["status"], "valid"
        )

    def test_expiry_and_unknown_expiration_never_return_token(self):
        self.save(now=NOW - timedelta(days=31))
        with self.assertRaises(RuntimeError):
            read_token(self.settings, now=NOW)
        saved = read_private_json(Path(self.settings["tokenFile"]), self.root)
        saved["saved_at_utc"] = "invalid"
        save_private_json(Path(self.settings["tokenFile"]), saved, self.root)
        with self.assertRaises(RuntimeError):
            read_token(self.settings, now=NOW)

    def test_world_readable_or_symlink_credentials_are_rejected(self):
        self.save()
        path = Path(self.settings["tokenFile"])
        path.chmod(0o644)
        with self.assertRaises(RuntimeError):
            read_token(self.settings, now=NOW)
        path.chmod(0o600)
        link = self.root / "link.json"
        link.symlink_to(path)
        with self.assertRaises(RuntimeError):
            read_private_json(link, self.root)

    def test_unsafe_directory_or_outside_private_root_is_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(RuntimeError):
            self.save()
        self.root.chmod(0o700)
        with self.assertRaises(RuntimeError):
            save_private_json(self.root.parent / "outside.json", {}, self.root)

    def test_refresh_replaces_both_tokens_with_matching_app_and_no_secret_in_result(
        self,
    ):
        self.save(now=NOW - timedelta(days=29))
        save_private_json(
            Path(self.settings["secretFile"]),
            {
                "format": "baidu-mcp-linux-secret-v1",
                "app_key": "example",
                "secret_key": "artificial-secret",
            },
            self.root,
        )
        calls = []

        def request(fields):
            calls.append(fields)
            return {
                "access_token": "new-artificial-access",
                "refresh_token": "new-artificial-refresh",
                "expires_in": 2592000,
            }

        result = ensure_authorization(self.settings, now=NOW, request=request)
        self.assertEqual(result["refreshAction"], "refreshed")
        self.assertEqual(read_token(self.settings, now=NOW), "new-artificial-access")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("artificial", json.dumps(result))
        ensure_authorization(self.settings, now=NOW, request=request)
        self.assertEqual(len(calls), 1)

    def test_missing_materials_keep_unexpired_token_but_not_expired_token(self):
        self.save(now=NOW - timedelta(days=29))
        result = ensure_authorization(self.settings, now=NOW)
        self.assertEqual(result["refreshAction"], "unavailable")
        self.assertEqual(read_token(self.settings, now=NOW), "artificial-access")
        with self.assertRaises(RuntimeError):
            read_token(self.settings, now=NOW + timedelta(days=2))

    def test_pending_refresh_is_retained_and_prevents_another_rotation(self):
        self.save(now=NOW - timedelta(days=29))
        save_private_json(
            Path(self.settings["secretFile"]),
            {
                "format": "baidu-mcp-linux-secret-v1",
                "app_key": "example",
                "secret_key": "secret",
            },
            self.root,
        )
        save_private_json(
            self.root / "token.json.pending-refresh",
            {"recovery": "retained"},
            self.root,
        )

        def request(fields):
            self.fail("Must not rotate with pending credentials")

        result = ensure_authorization(self.settings, now=NOW, request=request)
        self.assertEqual(
            result["refreshFailure"], "pending_credentials_recovery_required"
        )
        self.assertTrue((self.root / "token.json.pending-refresh").exists())

    def test_refresh_transport_error_cannot_expose_sensitive_message(self):
        self.save(now=NOW - timedelta(days=29))
        save_private_json(
            Path(self.settings["secretFile"]),
            {
                "format": "baidu-mcp-linux-secret-v1",
                "app_key": "example",
                "secret_key": "secret",
            },
            self.root,
        )

        def request(fields):
            raise OSError("access_token=artificial-access")

        result = ensure_authorization(self.settings, now=NOW, request=request)
        self.assertNotIn("artificial", json.dumps(result))
        self.assertEqual(result["refreshAction"], "failed")

    def test_settings_are_explicit_linux_and_private(self):
        value = {
            **self.settings,
            "python": sys.executable,
            "officialDir": "/example",
            "bridge": "/example/bridge.js",
        }
        save_private_json(self.root / "settings.json", value, self.root)
        self.assertEqual(
            load_settings(self.root / "settings.json")["platform"], "linux"
        )
        value["platform"] = "windows"
        save_private_json(self.root / "settings.json", value, self.root)
        with self.assertRaises(RuntimeError):
            load_settings(self.root / "settings.json")

    def test_roots_explicit_then_environment_then_supplied_toml(self):
        path = Path(self.temp.name) / "workspace.toml"
        path.write_text(
            '[roots]\nCODE_ROOT="/code"\nDATA_ROOT="/data"\nCONFIG_ROOT="/config"\n'
        )
        result = resolve_roots({"DATA_ROOT": "/explicit"}, {"DATA_ROOT": "/env"}, path)
        self.assertEqual(result["DATA_ROOT"], Path("/explicit"))
        self.assertEqual(result["CONFIG_ROOT"], Path("/config"))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(sys.platform == 'linux', 'Linux backend tests')
class LinuxProviderTests(unittest.TestCase):
    setUp = LinuxAuthorizationTests.setUp
    save = LinuxAuthorizationTests.save

    def test_provider_lease_enforces_expiry_before_background_check(self):
        from authorization import AuthorizationProvider
        import time

        self.save(now=datetime.now(timezone.utc), expires=2)
        with patch(
            "linux_authorization.utcnow", return_value=datetime.now(timezone.utc)
        ):
            provider = AuthorizationProvider(
                Path(__file__).resolve().parents[1] / "scripts", self.settings
            )
            with provider.lease() as token:
                self.assertEqual(token, "artificial-access")
            provider.next_check = time.monotonic() + 86400
            with patch(
                "linux_authorization.utcnow",
                return_value=datetime.now(timezone.utc) + timedelta(seconds=3),
            ):
                with self.assertRaises(RuntimeError):
                    with provider.lease():
                        self.fail("Expired token leased")

    def test_provider_never_uses_cached_token_after_file_permission_change(self):
        from authorization import AuthorizationProvider

        self.save(now=datetime.now(timezone.utc))
        provider = AuthorizationProvider(
            Path(__file__).resolve().parents[1] / "scripts", self.settings
        )
        Path(self.settings["tokenFile"]).chmod(0o644)
        with self.assertRaises(RuntimeError):
            with provider.lease():
                self.fail("Unsafe cached token leased")


@unittest.skipUnless(sys.platform == 'linux', 'Linux backend tests')
class LinuxConcurrencyTests(unittest.TestCase):
    setUp = LinuxAuthorizationTests.setUp
    save = LinuxAuthorizationTests.save

    def materials(self):
        self.save(now=NOW - timedelta(days=29))
        save_private_json(
            Path(self.settings["secretFile"]),
            {
                "format": "baidu-mcp-linux-secret-v1",
                "app_key": "example",
                "secret_key": "secret",
            },
            self.root,
        )

    def test_manual_reauthorization_waits_for_refresh_and_wins_after_it(self):
        import threading
        import concurrent.futures

        self.materials()
        entered = threading.Event()
        release = threading.Event()

        def request(fields):
            entered.set()
            release.wait(3)
            return {
                "access_token": "rotated-old",
                "refresh_token": "rotated-refresh",
                "expires_in": 2592000,
            }

        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            refresh = pool.submit(
                ensure_authorization, self.settings, now=NOW, request=request
            )
            self.assertTrue(entered.wait(2))
            manual = pool.submit(
                save_authorization,
                self.settings,
                "user-new",
                "user-refresh",
                2592000,
                now=NOW,
                replace=True,
            )
            try:
                with self.assertRaises(concurrent.futures.TimeoutError):
                    manual.result(timeout=0.1)
            finally:
                release.set()
            refresh.result()
            manual.result()
        self.assertEqual(read_token(self.settings, now=NOW), "user-new")

    def test_failed_refresh_publication_preserves_pending_and_never_rotates_again(self):
        self.materials()
        from linux_authorization import os as auth_os

        original = auth_os.replace

        def fail_pending(source, target):
            if str(source).endswith(".pending-refresh"):
                raise OSError("synthetic disk failure")
            return original(source, target)

        def request(fields):
            return {
                "access_token": "new-pending",
                "refresh_token": "new-refresh",
                "expires_in": 2592000,
            }

        with patch("linux_authorization.os.replace", side_effect=fail_pending):
            result = ensure_authorization(self.settings, now=NOW, request=request)
        self.assertEqual(result["refreshAction"], "failed")
        pending = self.root / "token.json.pending-refresh"
        self.assertEqual(
            read_private_json(pending, self.root)["access_token"], "new-pending"
        )

        def forbidden(fields):
            self.fail("Must not repeat refresh")

        result = ensure_authorization(self.settings, now=NOW, request=forbidden)
        self.assertEqual(
            result["refreshFailure"], "pending_credentials_recovery_required"
        )


@unittest.skipUnless(sys.platform == 'linux', 'Linux backend tests')
class LinuxProcessRefreshTests(unittest.TestCase):
    setUp = LinuxAuthorizationTests.setUp
    save = LinuxAuthorizationTests.save

    def test_two_processes_exchange_refresh_token_only_once(self):
        import multiprocessing
        import time

        self.save(now=NOW - timedelta(days=29))
        save_private_json(
            Path(self.settings["secretFile"]),
            {
                "format": "baidu-mcp-linux-secret-v1",
                "app_key": "example",
                "secret_key": "secret",
            },
            self.root,
        )
        context = multiprocessing.get_context("fork")
        barrier = context.Barrier(2)
        count = self.root / "requests.txt"

        def worker():
            def request(fields):
                with count.open("a") as stream:
                    stream.write("request\n")
                time.sleep(0.1)
                return {
                    "access_token": "process-new",
                    "refresh_token": "process-refresh",
                    "expires_in": 2592000,
                }

            barrier.wait(timeout=3)
            ensure_authorization(self.settings, now=NOW, request=request)

        processes = [context.Process(target=worker) for _ in range(2)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join()
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(count.read_text(), "request\n")


class AuthorizationResultTests(unittest.TestCase):
    def test_official_result_url_is_parsed_without_accepting_other_hosts_or_duplicate_tokens(
        self,
    ):
        from linux_authorization import parse_authorization_result

        access, refresh, lifetime = parse_authorization_result(
            "https://openapi.baidu.com/oauth/2.0/login_success#access_token=synthetic&expires_in=2592000"
        )
        self.assertEqual((access, refresh, lifetime), ("synthetic", "", 2592000))
        for url in (
            "https://example.invalid/#access_token=synthetic&expires_in=2592000",
            "https://openapi.baidu.com/oauth/2.0/login_success#access_token=a&access_token=b&expires_in=100",
        ):
            with self.assertRaises(RuntimeError):
                parse_authorization_result(url)
