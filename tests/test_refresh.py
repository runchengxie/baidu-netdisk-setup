import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == 'nt' and shutil.which('pwsh'), 'Windows required')
class RefreshTests(unittest.TestCase):
    def run_case(self, body):
        with tempfile.TemporaryDirectory(prefix='baidu-refresh-') as folder:
            env = {k: v for k, v in os.environ.items() if not k.startswith('BAIDU_MCP_')}
            env['REFRESH_ROOT'] = folder
            env['REFRESH_MODULE'] = str(Path(__file__).resolve().parents[1] / 'scripts' / 'refresh.ps1')
            script = """
$ErrorActionPreference='Stop'
. $env:REFRESH_MODULE
$s=@{tokenFile=(Join-Path $env:REFRESH_ROOT 'token.json');secretFile=(Join-Path $env:REFRESH_ROOT 'secret.json');appKey='example'}
$now=[DateTimeOffset]::UtcNow
$a=ConvertTo-SecureString 'fake-old-access' -AsPlainText -Force
$r=ConvertTo-SecureString 'fake-old-refresh' -AsPlainText -Force
@{access_token=(ConvertFrom-SecureString $a);refresh_token=(ConvertFrom-SecureString $r);expires_in=3600;saved_at_utc=$now.AddMinutes(-30).ToString('o')}|ConvertTo-Json|Set-Content $s.tokenFile
$key=ConvertTo-SecureString 'fake-app-secret' -AsPlainText -Force
Save-BaiduAppSecret -AppKey example -Secret $key -SecretFile $s.secretFile
$before=[IO.File]::ReadAllText($s.tokenFile)
""" + body
            result = subprocess.run(['pwsh', '-NoProfile', '-Command', script], env=env,
                                    capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('fake-app-secret', result.stdout + result.stderr)
            return json.loads(result.stdout)

    def test_due_refresh_encrypts_both_tokens_and_advances_expiry(self):
        result = self.run_case("""
$result=Invoke-BaiduEnsureAuthorization -Settings $s -Request {
 param($fields)
 if($fields.client_id -ne 'example' -or $fields.client_secret -ne 'fake-app-secret' -or $fields.refresh_token -ne 'fake-old-refresh'){throw 'Wrong request'}
 @{access_token='fake-new-access';refresh_token='fake-new-refresh';expires_in=2592000}
}
$saved=Get-Content -Raw $s.tokenFile|ConvertFrom-Json
$a=ConvertTo-SecureString $saved.access_token;$p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($a)
try{$matches=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($p) -eq 'fake-new-access'}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}
@{result=$result;tokenMatches=$matches;plaintextAbsent=([IO.File]::ReadAllText($s.tokenFile) -notmatch 'fake-new');lifetime=$saved.expires_in}|ConvertTo-Json -Depth 4 -Compress
""")
        self.assertEqual(result['result']['refreshAction'], 'refreshed')
        self.assertEqual(result['result']['status'], 'valid')
        self.assertTrue(result['tokenMatches'])
        self.assertTrue(result['plaintextAbsent'])
        self.assertEqual(result['lifetime'], 2592000)

    def test_fresh_token_does_not_call_refresh_endpoint(self):
        result = self.run_case("""
$saved=Get-Content -Raw $s.tokenFile|ConvertFrom-Json;$saved.expires_in=2592000
$saved|ConvertTo-Json|Set-Content $s.tokenFile
$result=Invoke-BaiduEnsureAuthorization -Settings $s -Request {throw 'Must not refresh'}
$result|ConvertTo-Json -Compress
""")
        self.assertEqual(result['refreshAction'], 'not_due')

    def test_network_and_invalid_response_preserve_original(self):
        for request in ("{throw 'fake-app-secret'}", "{@{access_token='fake-new-access';expires_in=3600}}"):
            result = self.run_case(f"""
$result=Invoke-BaiduEnsureAuthorization -Settings $s -Request {request}
@{{result=$result;unchanged=([IO.File]::ReadAllText($s.tokenFile) -eq $before)}}|ConvertTo-Json -Depth 4 -Compress
""")
            self.assertTrue(result['unchanged'])
            self.assertEqual(result['result']['refreshAction'], 'failed')

    def test_revoked_grant_is_actionable_without_credential_echo(self):
        result = self.run_case("""
$result=Invoke-BaiduEnsureAuthorization -Settings $s -Request {@{error='invalid_grant';error_description='fake-app-secret'}}
@{result=$result;unchanged=([IO.File]::ReadAllText($s.tokenFile) -eq $before)}|ConvertTo-Json -Depth 4 -Compress
""")
        self.assertEqual(result['result']['refreshFailure'], 'reauthorization_required')
        self.assertTrue(result['unchanged'])

    def test_wrong_secret_is_reported_without_destroying_authorization(self):
        result = self.run_case("""
$result=Invoke-BaiduEnsureAuthorization -Settings $s -Request {@{error='invalid_client';error_description='fake-app-secret'}}
@{result=$result;unchanged=([IO.File]::ReadAllText($s.tokenFile) -eq $before)}|ConvertTo-Json -Depth 4 -Compress
""")
        self.assertEqual(result['result']['refreshFailure'], 'app_credentials_rejected')
        self.assertTrue(result['unchanged'])

    def test_missing_secret_and_wrong_app_do_not_exchange(self):
        for mutation, expected in (("Remove-Item $s.secretFile", 'missing_secret_file'),
                                   ("$s.appKey='other'", 'app_key_mismatch')):
            result = self.run_case(mutation + """
$result=Invoke-BaiduEnsureAuthorization -Settings $s -Request {throw 'Must not exchange'}
$result|ConvertTo-Json -Compress
""")
            self.assertEqual(result['refreshFailure'], expected)
            self.assertEqual(result['refreshAction'], 'unavailable')

    def test_expired_token_can_be_refreshed_before_launcher_refuses_it(self):
        result = self.run_case("""
$saved=Get-Content -Raw $s.tokenFile|ConvertFrom-Json;$saved.saved_at_utc=$now.AddDays(-2).ToString('o')
$saved|ConvertTo-Json|Set-Content $s.tokenFile
Invoke-BaiduEnsureAuthorization -Settings $s -Request {@{access_token='fake-new-access';refresh_token='fake-new-refresh';expires_in=2592000}}|ConvertTo-Json -Compress
""")
        self.assertEqual(result['status'], 'valid')
        self.assertEqual(result['refreshAction'], 'refreshed')

    def test_pending_saved_credentials_prevent_another_exchange(self):
        result = self.run_case("""
Copy-Item $s.tokenFile ($s.tokenFile+'.pending-refresh.json')
Invoke-BaiduEnsureAuthorization -Settings $s -Request {throw 'Must not exchange again'}|ConvertTo-Json -Compress
""")
        self.assertEqual(result['refreshFailure'], 'pending_credentials_recovery_required')

    def test_two_processes_exchange_only_once(self):
        result = self.run_case("""
$childScript=Join-Path $env:REFRESH_ROOT 'child.ps1'
@'
$ErrorActionPreference='Stop'
. $env:REFRESH_MODULE
$s=@{tokenFile=(Join-Path $env:REFRESH_ROOT 'token.json');secretFile=(Join-Path $env:REFRESH_ROOT 'secret.json');appKey='example'}
Invoke-BaiduEnsureAuthorization -Settings $s -Request {
 Add-Content (Join-Path $env:REFRESH_ROOT 'calls.txt') 'called'
 Start-Sleep -Seconds 2
 @{access_token='fake-new-access';refresh_token='fake-new-refresh';expires_in=2592000}
}|ConvertTo-Json -Compress
'@|Set-Content $childScript
$exe=(Get-Command pwsh).Source
$one=Start-Process $exe -WindowStyle Hidden -ArgumentList @('-NoProfile','-File',$childScript) -PassThru -RedirectStandardOutput (Join-Path $env:REFRESH_ROOT 'one.json') -RedirectStandardError (Join-Path $env:REFRESH_ROOT 'one.err')
$two=Start-Process $exe -WindowStyle Hidden -ArgumentList @('-NoProfile','-File',$childScript) -PassThru -RedirectStandardOutput (Join-Path $env:REFRESH_ROOT 'two.json') -RedirectStandardError (Join-Path $env:REFRESH_ROOT 'two.err')
$one.WaitForExit();$two.WaitForExit()
@{calls=@(Get-Content (Join-Path $env:REFRESH_ROOT 'calls.txt')).Count;one=(Get-Content -Raw (Join-Path $env:REFRESH_ROOT 'one.json')|ConvertFrom-Json);two=(Get-Content -Raw (Join-Path $env:REFRESH_ROOT 'two.json')|ConvertFrom-Json)}|ConvertTo-Json -Depth 4 -Compress
""")
        self.assertEqual(result['calls'], 1)
        self.assertEqual(result['one']['status'], 'valid')
        self.assertEqual(result['two']['status'], 'valid')


if __name__ == '__main__':
    unittest.main()
