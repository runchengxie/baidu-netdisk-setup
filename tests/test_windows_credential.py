import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == 'nt' and shutil.which('pwsh'), 'Windows + PowerShell required')
class CredentialTests(unittest.TestCase):
    def run_helper(self, saved_at, lifetime, mode='status'):
        with tempfile.TemporaryDirectory(prefix='baidu-credential-test-') as directory:
            path = Path(directory) / 'encrypted-fixture.json'
            env = {**os.environ, 'BAIDU_TEST_FILE': str(path), 'BAIDU_TEST_TIME': saved_at, 'BAIDU_TEST_LIFETIME': str(lifetime)}
            # Only an artificial token is encrypted. No real account is used.
            script = "$s=ConvertTo-SecureString 'artificial-unit-test-credential' -AsPlainText -Force; @{access_token=(ConvertFrom-SecureString $s);saved_at_utc=$env:BAIDU_TEST_TIME;expires_in=[long]$env:BAIDU_TEST_LIFETIME}|ConvertTo-Json|Set-Content -LiteralPath $env:BAIDU_TEST_FILE -Encoding utf8"
            subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-Command', script], env=env, capture_output=True, check=True)
            helper = Path(__file__).resolve().parents[1] / 'scripts' / 'read-credential.ps1'
            return subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-File', str(helper),
                                   '-TokenFile', str(path), '-Mode', mode], capture_output=True, text=True)

    def test_utc_is_preserved(self):
        result = self.run_helper('2099-10-08T03:32:49.6030034Z', 30 * 86400)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['expiresAtUtc'], '2099-11-07T03:32:49.6030034Z')
        self.assertNotIn('artificial-unit-test-credential', result.stdout)

    def test_expired_refuses_decryption_output(self):
        result = self.run_helper('2020-01-01T00:00:00Z', 86400, 'token')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), '')
        self.assertNotIn('artificial-unit-test-credential', result.stderr)


if __name__ == '__main__': unittest.main()
