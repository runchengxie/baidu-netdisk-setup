import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_linux_app_authorization as base_tests
from linux_app_authorization import exchange_app_authorization, parse_authorization_code


@unittest.skipUnless(sys.platform == "linux", "Linux backend tests")
class AuthorizationDiagnosticsTests(unittest.TestCase):
    setUp = base_tests.OriginalAppAuthorizationTests.setUp
    request = base_tests.OriginalAppAuthorizationTests.request

    def test_oauth_client_rejection_preserves_safe_code_without_description(self):
        def request(fields):
            return {
                "error": "invalid_client",
                "error_description": "secret=synthetic-secret code=synthetic-code",
            }

        with self.assertRaises(RuntimeError) as caught:
            exchange_app_authorization(
                self.profile, "synthetic-secret", "synthetic-code", request=request
            )
        self.assertEqual(getattr(caught.exception, "code", None), "invalid_client")
        self.assertEqual(getattr(caught.exception, "phase", None), "exchange")
        self.assertNotIn("synthetic", str(caught.exception))

    def test_http_error_body_is_classified_without_exposing_echoed_credentials(self):
        def request(fields):
            raise urllib.error.HTTPError(
                "https://example.invalid/?code=synthetic-code",
                400,
                "bad",
                {},
                io.BytesIO(
                    b'{"error":"invalid_grant","error_description":"code=synthetic-code secret=synthetic-secret"}'
                ),
            )

        with self.assertRaises(RuntimeError) as caught:
            exchange_app_authorization(
                self.profile, "synthetic-secret", "synthetic-code", request=request
            )
        self.assertEqual(getattr(caught.exception, "code", None), "invalid_grant")
        self.assertNotIn("synthetic", str(caught.exception))

    def test_network_failures_are_distinct_from_oauth_rejections(self):
        def request(fields):
            raise urllib.error.URLError("synthetic-secret")

        with self.assertRaises(RuntimeError) as caught:
            exchange_app_authorization(
                self.profile, "synthetic-secret", "synthetic-code", request=request
            )
        self.assertEqual(getattr(caught.exception, "code", None), "network_failure")
        self.assertNotIn("synthetic", str(caught.exception))

    def test_missing_state_and_mismatch_are_distinct_from_invalid_raw_code(self):
        cases = [
            (
                "https://openapi.baidu.com/oauth/2.0/login_success?code=synthetic",
                "authorization_state_missing",
            ),
            (
                "https://openapi.baidu.com/oauth/2.0/login_success?code=synthetic&state=wrong",
                "authorization_state_mismatch",
            ),
            ("code with spaces", "invalid_code"),
        ]
        for value, want in cases:
            with self.assertRaises(RuntimeError) as caught:
                parse_authorization_code(value, "expected")
            self.assertEqual(getattr(caught.exception, "code", None), want)
            self.assertNotIn("synthetic", str(caught.exception))
        self.assertEqual(
            parse_authorization_code("  synthetic-code\n", "expected"), "synthetic-code"
        )

    def test_missing_refresh_has_its_own_diagnostic(self):
        def request(fields):
            result = self.request(fields)
            result.pop("refresh_token")
            return result

        with self.assertRaises(RuntimeError) as caught:
            exchange_app_authorization(
                self.profile, "synthetic-secret", "synthetic-code", request=request
            )
        self.assertEqual(
            getattr(caught.exception, "code", None), "refresh_token_missing"
        )

    def test_cli_prints_safe_classification_instead_of_discarding_it(self):
        spec = importlib.util.spec_from_file_location(
            "diagnostic_helper",
            Path(__file__).resolve().parents[1] / "scripts" / "credential-helper.py",
        )
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        with (
            patch.object(helper.sys.stdin, "isatty", return_value=True),
            patch.object(
                helper.getpass,
                "getpass",
                side_effect=["synthetic-secret", "code with spaces"],
            ),
            patch.object(helper.sys, "stderr", new_callable=io.StringIO) as stderr,
            patch.object(helper.sys, "stdout", new_callable=io.StringIO),
        ):
            result = helper.main(
                [
                    "--settings",
                    str(self.root / "original-app-settings.json"),
                    "authorize-app",
                ]
            )
        self.assertEqual(result, 1)
        self.assertIn("invalid_code", stderr.getvalue())
        self.assertNotIn("synthetic", stderr.getvalue())

    def test_opaque_authorization_code_preserves_encoded_token_characters(self):
        self.assertEqual(parse_authorization_code("aB+/cD==", "expected"), "aB+/cD==")
        for value in (
            "https://example.invalid/?code=a",
            "http://example.invalid/code",
            "unsafe\x00code",
        ):
            with self.assertRaises(RuntimeError):
                parse_authorization_code(value, "expected")

    def test_unknown_server_error_name_is_not_echoed(self):
        def request(fields):
            return {"error": "synthetic-secret", "error_description": "synthetic-code"}

        with self.assertRaises(RuntimeError) as caught:
            exchange_app_authorization(
                self.profile, "synthetic-secret", "synthetic-code", request=request
            )
        self.assertEqual(getattr(caught.exception, "code", None), "oauth_rejected")
        self.assertNotIn("synthetic", str(caught.exception))
