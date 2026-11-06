import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from linux_config import save_private_json
from linux_authorization import save_authorization


@unittest.skipUnless(sys.platform == "linux" and shutil.which("node"), "Linux and Node required")
class RemoteLinuxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private"
        self.root.mkdir(mode=0o700)
        source = Path(__file__).resolve().parents[1] / "scripts"
        for name in (
            "start-remote.mjs",
            "remote-worker.mjs",
            "platform-config.mjs",
            "session-relay.mjs",
            "credential-helper.py",
            "linux_config.py",
            "linux_authorization.py",
        ):
            shutil.copyfile(source / name, self.root / name)
        bridge = self.root / "fake-bridge.mjs"
        bridge.write_text("""
import {createInterface} from 'node:readline';
const token=new URL(process.argv[2]).searchParams.get('access_token');
process.stderr.write('fixture access_token='+token+'\\n');
const lines=createInterface({input:process.stdin});
lines.on('line',line=>{const m=JSON.parse(line); if(m.id!==undefined)
process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:m.id,result:{fixture:true}})+'\\n');});
""")
        self.settings = {
            "platform": "linux",
            "deploymentRoot": str(self.root),
            "tokenFile": str(self.root / "token.json"),
            "secretFile": str(self.root / "secret.json"),
            "appKey": "",
            "python": sys.executable,
            "officialDir": str(self.root / "unused"),
            "bridge": str(bridge),
        }
        save_private_json(self.root / "settings.json", self.settings, self.root)
        save_authorization(
            self.settings,
            "artificial-remote-secret",
            "",
            2592000,
            now=datetime.now(timezone.utc),
        )
        self.process = subprocess.Popen(
            ["node", str(self.root / "start-remote.mjs")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self.stop)
        response = self.call(1, "initialize")
        self.assertTrue(response.get("result", {}).get("fixture"))

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.communicate(timeout=5)

    def call(self, identity, method):
        self.process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": identity, "method": method}) + "\n"
        )
        self.process.stdin.flush()
        ready, _, _ = select.select([self.process.stdout], [], [], 5)
        self.assertTrue(ready, "Timed out waiting for fixture MCP")
        line = self.process.stdout.readline()
        return json.loads(line) if line else {}

    def test_bad_permissions_block_next_request_instead_of_using_cached_authorization(
        self,
    ):
        Path(self.settings["tokenFile"]).chmod(0o644)
        response = self.call(2, "tools/list")
        self.assertNotIn("result", response)

    def test_missing_or_malformed_credentials_block_next_request(self):
        Path(self.settings["tokenFile"]).write_text("malformed")
        response = self.call(2, "tools/list")
        self.assertNotIn("result", response)

    def test_bridge_diagnostics_do_not_reveal_token(self):
        self.process.stdin.close()
        self.process.stdin = None
        out, err = self.process.communicate(timeout=5)
        self.assertNotIn("artificial-remote-secret", out + err)
        self.assertIn("[REDACTED]", err)
