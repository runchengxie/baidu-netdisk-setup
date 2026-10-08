import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from policy import expiry_status, redact, remote_target, upload_policy


class PolicyTests(unittest.TestCase):
    def test_expired(self):
        now = datetime(2026, 10, 8, tzinfo=timezone.utc)
        self.assertEqual(expiry_status({'saved_at_utc': '2026-09-01T00:00:00Z', 'expires_in': 30 * 86400}, now)['status'], 'expired')

    def test_warning_and_unknown(self):
        now = datetime(2026, 10, 8, tzinfo=timezone.utc)
        self.assertEqual(expiry_status({'saved_at_utc': '2026-09-10T00:00:00Z', 'expires_in': 30 * 86400}, now)['status'], 'expiring')
        self.assertEqual(expiry_status({}, now)['status'], 'unknown')

    def test_redaction(self):
        value = redact('secret https://baidu.com/?access_token=other&x=1 Bearer hidden', 'secret')
        self.assertNotIn('secret', value)
        self.assertNotIn('other', value)
        self.assertNotIn('hidden', value)

    def test_target(self):
        self.assertEqual(remote_target('/资料/', 'a.txt'), '/资料/a.txt')
        for directory in ('relative', '/a/../b', '/a//b'):
            with self.assertRaises(ValueError): remote_target(directory, 'a.txt')

    def test_conflict_default(self):
        self.assertEqual(upload_policy(False), 0)
        self.assertEqual(upload_policy(True), 3)


if __name__ == '__main__':
    unittest.main()
