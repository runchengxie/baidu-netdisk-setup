import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
loader = importlib.util.spec_from_file_location(
    "install_linux", Path(__file__).resolve().parents[1] / "scripts/install-linux.py"
)
install = importlib.util.module_from_spec(loader)
loader.loader.exec_module(install)


@unittest.skipUnless(sys.platform == 'linux', 'Linux backend tests')
class LinuxInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.roots = {
            k: self.root / k.lower() for k in ("CODE_ROOT", "DATA_ROOT", "CONFIG_ROOT")
        }
        for path in self.roots.values():
            path.mkdir()

    def test_preparation_creates_stable_linux_paths_without_registration_or_tokens(
        self,
    ):
        settings = install.prepare(self.roots, prepare_only=True)
        deployment = Path(settings["deploymentRoot"])
        self.assertEqual(deployment.stat().st_mode & 0o777, 0o700)
        self.assertEqual((deployment / "settings.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(settings["platform"], "linux")
        self.assertTrue((deployment / "start-local.py").is_file())
        self.assertTrue((deployment / "platform-config.mjs").is_file())
        self.assertIn("/runtime/linux/", settings["officialDir"])
        self.assertFalse(Path(settings["tokenFile"]).exists())
        self.assertNotIn(".worktrees", json.dumps(settings))

    def test_rerun_preserves_private_application_settings(self):
        settings = install.prepare(self.roots, prepare_only=True)
        path = Path(settings["deploymentRoot"]) / "settings.json"
        value = json.loads(path.read_text())
        value["appKey"] = "example-app"
        path.write_text(json.dumps(value))
        path.chmod(0o600)
        latest = install.prepare(self.roots, prepare_only=True)
        self.assertEqual(latest["appKey"], "example-app")

    def test_unknown_deployment_is_preserved_and_rejected(self):
        target = self.roots["CONFIG_ROOT"] / "deployments" / "baidu-netdisk-mcp"
        target.mkdir(parents=True, mode=0o700)
        (target / "unknown.txt").write_text("preserve")
        with self.assertRaises(RuntimeError):
            install.prepare(self.roots, prepare_only=True)
        self.assertEqual((target / "unknown.txt").read_text(), "preserve")

    def test_source_config_and_symlink_deployment_are_rejected(self):
        (self.roots["CONFIG_ROOT"] / ".git").mkdir()
        with self.assertRaises(RuntimeError):
            install.prepare(self.roots, prepare_only=True)
