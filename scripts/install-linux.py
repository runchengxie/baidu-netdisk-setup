#!/usr/bin/env python3
"""Install pinned official MCPs on Linux; preparation does not require credentials."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from linux_config import load_settings, private_path, resolve_roots, save_private_json

REVISION = "b3983d330fea79c7b72e6b7014803e1830148d2c"
BRIDGE_VERSION = "0.14.3"
FILES = (
    "policy.py",
    "authorization.py",
    "linux_config.py",
    "linux_authorization.py",
    "linux_app_authorization.py",
    "credential-helper.py",
    "platform-config.mjs",
    "session-relay.mjs",
    "remote-worker.mjs",
    "start-remote.mjs",
    "start-local.py",
    "check-mcp.py",
)


def run(argv, **kwargs):
    return subprocess.run([str(v) for v in argv], check=True, **kwargs)


def verify_official_checkout(official, revision):
    head = run(
        ["git", "-C", official, "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    if head != revision:
        raise RuntimeError(
            "Pinned official revision mismatch; existing checkout preserved"
        )
    changes = run(
        [
            "git",
            "-C",
            official,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=no",
        ],
        capture_output=True,
        text=True,
    ).stdout
    for record in changes.split("\0"):
        if not record:
            continue
        path = Path(record[3:])
        # This revision tracks generated caches. The Linux launcher selects an
        # external pycache prefix, so it never loads these tracked cache files.
        if (
            record[:2] not in (" M", "M ", "MM")
            or "__pycache__" not in path.parts
            or path.suffix != ".pyc"
            or not (Path(official) / path).is_file()
            or (Path(official) / path).is_symlink()
        ):
            raise RuntimeError(
                "Official source modifications preserved; refusing installation"
            )


def _no_source_or_links(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise RuntimeError("Absolute installation paths required")
    for item in (path, *path.parents):
        if item.is_symlink() or (item / ".git").exists() and item != Path.home():
            raise RuntimeError("Installation paths must be outside source and symlinks")


def prepare(roots, *, prepare_only=False, skip_registration=False):
    if sys.platform != "linux":
        raise RuntimeError("This installer is for Linux")
    data = Path(roots["DATA_ROOT"]) / "baidu-netdisk-mcp"
    runtime = data / "runtime" / "linux"
    deployment = Path(roots["CONFIG_ROOT"]) / "deployments" / "baidu-netdisk-mcp"
    for path in (runtime, deployment):
        _no_source_or_links(path)
    existed = deployment.exists()
    if (
        existed
        and not (deployment / "settings.json").exists()
        and any(deployment.iterdir())
    ):
        raise RuntimeError("Unknown existing deployment preserved")
    deployment.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_path(deployment / "settings.json", deployment)
    old = (
        load_settings(deployment / "settings.json")
        if (deployment / "settings.json").exists()
        else {}
    )
    if old and (
        old.get("installation") != "baidu-netdisk-linux-v1"
        or old.get("dataRoot") != str(roots["DATA_ROOT"])
        or old.get("configRoot") != str(roots["CONFIG_ROOT"])
    ):
        raise RuntimeError("Existing deployment belongs to another installation")
    if (
        runtime.exists()
        and any(runtime.iterdir())
        and not (runtime / "installation.json").is_file()
    ):
        raise RuntimeError("Unknown existing Linux runtime preserved")
    runtime.mkdir(parents=True, exist_ok=True)
    marker = runtime / "installation.json"
    identity = {
        "installation": "baidu-netdisk-linux-v1",
        "deploymentRoot": str(deployment),
    }
    if marker.exists():
        if marker.is_symlink() or json.loads(marker.read_text()) != identity:
            raise RuntimeError("Existing runtime belongs to another installation")
    else:
        marker.write_text(json.dumps(identity) + "\n")
    official = runtime / "official-mcp"
    official_dir = official / "src" / "baidu-netdisk"
    bridge = runtime / "node_modules" / "mcp-remote" / "dist" / "proxy.js"
    python = official_dir / ".venv" / "bin" / "python"
    settings = {
        **old,
        "installation": "baidu-netdisk-linux-v1",
        "platform": "linux",
        "deploymentRoot": str(deployment),
        "dataRoot": str(roots["DATA_ROOT"]),
        "configRoot": str(roots["CONFIG_ROOT"]),
        "python": str(python),
        "tokenFile": old.get("tokenFile", str(deployment / "authorization.json")),
        "secretFile": old.get("secretFile", str(deployment / "app-secret.json")),
        "appKey": old.get("appKey", ""),
        "officialDir": str(official_dir),
        "bridge": str(bridge),
    }
    for key in ("tokenFile", "secretFile"):
        private_path(settings[key], deployment)
    for name in FILES:
        target = deployment / name
        if target.is_symlink() or target.exists() and not target.is_file():
            raise RuntimeError("Unexpected launcher path preserved")
        # Only an identified deployment may replace its own launchers.
        shutil.copyfile(Path(__file__).parent / name, target)
        target.chmod(0o600)
    save_private_json(deployment / "settings.json", settings, deployment)
    if prepare_only:
        return settings
    if not official.exists():
        run(
            [
                "git",
                "clone",
                "--no-checkout",
                "https://github.com/baidu-netdisk/mcp.git",
                official,
            ]
        )
        run(["git", "-C", official, "checkout", "--detach", REVISION])
    verify_official_checkout(official, REVISION)
    run(
        [
            "npm",
            "install",
            "--prefix",
            runtime,
            "--save-exact",
            "mcp-remote@" + BRIDGE_VERSION,
        ]
    )
    run(["uv", "sync", "--frozen", "--python", "3.12", "--project", official_dir])
    if not python.is_file() or not bridge.is_file():
        raise RuntimeError("Runtime dependencies missing")
    if not skip_registration:
        node = shutil.which("node")
        codex = shutil.which("codex")
        if not node or not codex:
            raise RuntimeError("Node and Codex commands required for registration")
        run(
            [
                codex,
                "mcp",
                "add",
                "baidu-netdisk",
                "--",
                node,
                deployment / "start-remote.mjs",
            ]
        )
        run(
            [
                codex,
                "mcp",
                "add",
                "baidu-netdisk-local-uploader",
                "--",
                python,
                deployment / "start-local.py",
            ]
        )
    return settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-config", type=Path)
    parser.add_argument("--code-root")
    parser.add_argument("--data-root")
    parser.add_argument("--config-root")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--skip-registration", action="store_true")
    args = parser.parse_args(argv)
    try:
        roots = resolve_roots(
            {
                k.upper(): v
                for k, v in vars(args).items()
                if k in ("code_root", "data_root", "config_root")
            },
            workspace=args.workspace_config,
        )
        settings = prepare(
            roots,
            prepare_only=args.prepare_only,
            skip_registration=args.skip_registration,
        )
        print(
            json.dumps(
                {
                    "status": "prepared" if args.prepare_only else "installed",
                    "deploymentRoot": settings["deploymentRoot"],
                    "registered": not args.prepare_only and not args.skip_registration,
                    "authenticated": False,
                }
            )
        )
        return 0
    except Exception:
        print(
            "Baidu Linux installation failed. Existing credentials and historical runtimes are preserved; inspect installation paths and dependencies.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
