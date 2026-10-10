import importlib.util
import json
import logging
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from authorization import AuthorizationProvider, install_log_redaction


class ProviderTests(unittest.TestCase):
    def test_daily_deadline_checks_and_reloads_authorization(self):
        values = iter(['old-artificial-token', 'new-artificial-token'])
        def execute(command, **kwargs):
            text = next(values) if command[-1] == 'token' else json.dumps({'status':'valid','refreshAction':'not_due'})
            return subprocess.CompletedProcess(command, 0, text, '')
        with patch('authorization.subprocess.run', side_effect=execute), patch('authorization.time.monotonic', return_value=1000) as clock:
            provider = AuthorizationProvider(Path('private'), {'powershell':'pwsh','tokenFile':'private/token.json'})
            clock.return_value = 80000
            with provider.lease() as token:
                self.assertEqual(token, 'old-artificial-token')
            clock.return_value = 87401
            with provider.lease() as token:
                self.assertEqual(token, 'new-artificial-token')

    def test_concurrent_file_replacement_during_read_reloads_latest_token(self):
        values = iter(['old-artificial-token', 'new-artificial-token'])
        def execute(command, **kwargs):
            text = next(values) if command[-1] == 'token' else json.dumps({'status':'valid','refreshAction':'not_due'})
            return subprocess.CompletedProcess(command, 0, text, '')
        with patch('authorization.subprocess.run', side_effect=execute), patch.object(AuthorizationProvider, 'file_stamp', side_effect=[1,2,2,2]):
            provider = AuthorizationProvider(Path('private'), {'powershell':'pwsh','tokenFile':'private/token.json'})
            self.assertEqual(provider.token, 'new-artificial-token')

    def test_credentials_are_redacted_before_log_handlers_wrap_lines(self):
        def execute(command, **kwargs):
            text = 'artificial-token-for-logging' if command[-1] == 'token' else json.dumps({'status':'valid','refreshAction':'not_due'})
            return subprocess.CompletedProcess(command, 0, text, '')
        previous = logging.getLogRecordFactory()
        with patch('authorization.subprocess.run', side_effect=execute):
            provider = AuthorizationProvider(Path('private'), {'powershell':'pwsh','tokenFile':'private/token.json'})
            install_log_redaction(provider)
            try:
                record = logging.getLogRecordFactory()('test', logging.WARNING, __file__, 1,
                    'Request failed: %s', ('https://example.invalid/?access_token=artificial-token-for-logging',), None)
                self.assertNotIn('artificial-token', record.getMessage())
                self.assertIn('[REDACTED]', record.getMessage())
            finally:
                logging.setLogRecordFactory(previous)

    def test_refresh_result_reloads_token_and_retains_old_redaction(self):
        tokens = iter(['old-artificial-token', 'new-artificial-token'])
        def execute(command, **kwargs):
            if command[-1] == 'token':
                return subprocess.CompletedProcess(command, 0, next(tokens), '')
            return subprocess.CompletedProcess(command, 0, json.dumps({'status':'valid','refreshAction':'not_due'}), '')
        with patch('authorization.subprocess.run', side_effect=execute):
            provider = AuthorizationProvider(Path('private'), {'powershell':'pwsh','tokenFile':'private/token.json'})
            provider.check()
            with provider.lease() as token:
                self.assertEqual(token, 'new-artificial-token')
            self.assertNotIn('artificial-token', provider.redact('old-artificial-token new-artificial-token'))

    def test_expired_authorization_stops_upload_without_exposing_credentials(self):
        def execute(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, json.dumps({'status':'expired','refreshAction':'failed','refreshFailure':'reauthorization_required'}), '')
        with patch('authorization.subprocess.run', side_effect=execute):
            with self.assertRaises(RuntimeError):
                AuthorizationProvider(Path('private'), {'powershell':'pwsh','tokenFile':'private/token.json'})


if __name__ == '__main__': unittest.main()
