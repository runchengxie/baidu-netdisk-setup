import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == 'nt' and shutil.which('pwsh'), 'Windows + PowerShell required')
class EnvTests(unittest.TestCase):
    def load(self, contents='', overrides=None):
        with tempfile.TemporaryDirectory(prefix='baidu-env-test-') as directory:
            root = Path(directory)
            (root / 'settings.json').write_text(json.dumps({'tokenFile': str(root / 'original.json')}), encoding='utf-8')
            (root / '.env').write_text(contents, encoding='utf-8')
            env = {key: value for key, value in os.environ.items() if not key.startswith('BAIDU_MCP_')}
            env.update(overrides or {})
            helper = Path(__file__).resolve().parents[1] / 'scripts' / 'load-settings.ps1'
            result = subprocess.run(['pwsh', '-NoProfile', '-File', str(helper), '-SettingsFile', str(root / 'settings.json')], env=env, capture_output=True, text=True, encoding='utf-8')
            return result, root

    def test_dotenv_quotes_unicode_and_relative_paths(self):
        result, root = self.load('# comment\nBAIDU_MCP_TOKEN_FILE="资料 #1.json"\nBAIDU_MCP_APP_KEY=example-app\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads(result.stdout)
        self.assertEqual(Path(settings['tokenFile']), root / '资料 #1.json')
        self.assertEqual(settings['appKey'], 'example-app')

    def test_environment_wins(self):
        result, root = self.load('BAIDU_MCP_TOKEN_FILE=from-file.json\n', {'BAIDU_MCP_TOKEN_FILE': 'from-process.json'})
        self.assertEqual(Path(json.loads(result.stdout)['tokenFile']), root / 'from-process.json')

    def test_empty_keeps_existing_settings(self):
        result, root = self.load('BAIDU_MCP_TOKEN_FILE=\nBAIDU_MCP_APP_KEY=\n')
        self.assertEqual(Path(json.loads(result.stdout)['tokenFile']), root / 'original.json')

    def test_reject_plaintext_secret_without_echoing(self):
        result, _ = self.load('BAIDU_MCP_SECRET_KEY=never-echo-this-secret\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('never-echo-this-secret', result.stdout + result.stderr)

    def test_reject_duplicates_and_mismatched_quotes(self):
        for value in ('BAIDU_MCP_APP_KEY=a\nBAIDU_MCP_APP_KEY=b\n', 'BAIDU_MCP_APP_KEY="unclosed\n'):
            result, _ = self.load(value)
            self.assertNotEqual(result.returncode, 0)

    def test_encrypted_secret_and_app_mismatch(self):
        with tempfile.TemporaryDirectory(prefix='baidu-secret-test-') as directory:
            path = Path(directory) / 'app-secret.json'
            module = Path(__file__).resolve().parents[1] / 'scripts' / 'config.ps1'
            env = {**os.environ, 'BAIDU_TEST_SECRET_FILE': str(path), 'BAIDU_TEST_CONFIG_MODULE': str(module)}
            script = ". $env:BAIDU_TEST_CONFIG_MODULE; $s=ConvertTo-SecureString 'artificial-unit-secret' -AsPlainText -Force; Save-BaiduAppSecret -AppKey example -Secret $s -SecretFile $env:BAIDU_TEST_SECRET_FILE; @{ready=(Get-BaiduRefreshStatus -Settings @{appKey='example';secretFile=$env:BAIDU_TEST_SECRET_FILE} -HasRefreshToken $true);mismatch=(Get-BaiduRefreshStatus -Settings @{appKey='other';secretFile=$env:BAIDU_TEST_SECRET_FILE} -HasRefreshToken $true)}|ConvertTo-Json -Depth 3 -Compress"
            result = subprocess.run(['pwsh', '-NoProfile', '-Command', script], env=env, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            self.assertTrue(value['ready']['refreshMaterialsReady'])
            self.assertTrue(value['ready']['automaticRefresh'])
            self.assertEqual(value['mismatch']['refreshConfigurationStatus'], 'app_key_mismatch')
            self.assertNotIn('artificial-unit-secret', path.read_text(encoding='utf-8-sig'))

    def test_secret_cannot_be_written_in_project_repository(self):
        with tempfile.TemporaryDirectory(prefix='baidu-source-guard-') as directory:
            root = Path(directory)
            (root / '.git').mkdir()
            target = root / 'app-secret.json'
            module = Path(__file__).resolve().parents[1] / 'scripts' / 'config.ps1'
            env = {**os.environ, 'BAIDU_TEST_SECRET_FILE': str(target), 'BAIDU_TEST_CONFIG_MODULE': str(module)}
            script = "$ErrorActionPreference='Stop'; . $env:BAIDU_TEST_CONFIG_MODULE; $s=ConvertTo-SecureString 'artificial-unit-secret' -AsPlainText -Force; Save-BaiduAppSecret -AppKey example -Secret $s -SecretFile $env:BAIDU_TEST_SECRET_FILE"
            result = subprocess.run(['pwsh', '-NoProfile', '-Command', script], env=env, capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(target.exists())


if __name__ == '__main__': unittest.main()
