"""Wrap the pinned official uploader without modifying upstream source."""

import contextvars
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from policy import redact, remote_target, upload_policy
from authorization import AuthorizationProvider, install_log_redaction


def load_launcher_settings(here):
    path = Path(os.environ.get("BAIDU_MCP_SETTINGS_FILE", str(here / "settings.json")))
    base = json.loads(path.read_text(encoding="utf-8-sig"))
    if base.get("platform") == "linux":
        from linux_config import load_settings

        return load_settings(path)
    if path != here / "settings.json":
        raise RuntimeError("Alternate settings selection requires the Linux backend")
    loaded = subprocess.run(
        [
            base["powershell"],
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(here / "load-settings.ps1"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if loaded.returncode:
        raise RuntimeError("Configuration unavailable")
    return json.loads(loaded.stdout)


def configure_bytecode_cache(settings):
    if settings.get("platform") != "linux":
        return
    data_root = Path(settings["dataRoot"])
    if not data_root.is_absolute() or ".." in data_root.parts:
        raise RuntimeError("Absolute data root required for bytecode cache")
    cache = data_root / "baidu-netdisk-mcp" / "runtime" / "linux" / "pycache"
    for parent in (cache, *cache.parents):
        if parent.is_symlink() or (parent / ".git").exists() and parent != Path.home():
            raise RuntimeError("Bytecode cache must be outside source and symlinks")
    cache.mkdir(parents=True, exist_ok=True)
    sys.pycache_prefix = str(cache)


def main():
    here = Path(__file__).resolve().parent
    settings = load_launcher_settings(here)
    configure_bytecode_cache(settings)
    authorization = AuthorizationProvider(here, settings)
    install_log_redaction(authorization)

    class SafeStream:
        def __init__(self, stream):
            self.stream = stream

        def write(self, text):
            return self.stream.write(authorization.redact(text))

        def flush(self):
            return self.stream.flush()

        def __getattr__(self, name):
            return getattr(self.stream, name)

    sys.stderr = SafeStream(sys.stderr)
    upstream = Path(settings["officialDir"]) / "fileupload_tool.py"
    spec = importlib.util.spec_from_file_location("official_baidu_upload", upstream)
    official = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(official)
    # Do not expose upstream upload_file, whose rtype=3 overwrites silently.
    from mcp.server.fastmcp import FastMCP

    api_class = official.fileupload_api.FileuploadApi
    naming = contextvars.ContextVar("upload_naming", default=0)
    for method_name in ("xpanfileprecreate", "xpanfilecreate"):
        original = getattr(api_class, method_name)

        def guarded(self, *args, _original=original, **kwargs):
            kwargs["rtype"] = naming.get()
            return _original(self, *args, **kwargs)

        setattr(api_class, method_name, guarded)
    mcp = FastMCP("Baidu local uploader with explicit overwrite")

    @mcp.tool()
    def upload_file(
        local_file_path: str,
        remote_directory: str = "/来自：mcp_server",
        overwrite: bool = False,
    ) -> dict:
        """Upload a local file using the official SDK. remote_directory is a DIRECTORY, not a filename.
        Default rejects an existing filename. Set overwrite=true only with explicit user permission.
        No persisted resume state; interrupted uploads cannot be resumed by this tool.
        """
        try:
            with authorization.lease() as token:
                return perform_upload(
                    local_file_path, remote_directory, overwrite, token
                )
        except Exception:
            return {
                "status": "error",
                "message": "Authorization unavailable. Check refresh configuration or reauthorize.",
            }

    def perform_upload(local_file_path, remote_directory, overwrite, token):
        try:
            local = Path(local_file_path)
            target = remote_target(remote_directory, local.name)
            if not local.is_file():
                return {"status": "error", "message": "Local file does not exist"}
            if local.stat().st_size == 0:
                return {
                    "status": "error",
                    "message": "Empty-file upload is not supported by this wrapper",
                }
            # Read all pages to give an understandable conflict error before any upload.
            session = official.requests.Session()
            session.trust_env = False
            start = 0
            with session:
                while True:
                    response = session.get(
                        "https://pan.baidu.com/rest/2.0/xpan/file",
                        params={
                            "access_token": token,
                            "method": "list",
                            "dir": remote_directory.rstrip("/") or "/",
                            "start": start,
                            "limit": 1000,
                            "web": 0,
                            "folder": 0,
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                    listing = response.json()
                    if listing.get("errno") != 0:
                        return {
                            "status": "error",
                            "message": "Cannot inspect destination",
                            "errno": listing.get("errno"),
                        }
                    existing = next(
                        (f for f in listing.get("list", []) if f["path"] == target),
                        None,
                    )
                    if existing and (existing["isdir"] or not overwrite):
                        return {
                            "status": "conflict",
                            "message": "Destination exists; explicit overwrite permission required",
                            "remote_path": target,
                        }
                    if len(listing.get("list", [])) < 1000:
                        break
                    start += 1000
            flag = naming.set(upload_policy(overwrite))
            try:
                configuration = official.openapi_client.Configuration()
                configuration.connection_pool_maxsize = 10
                configuration.retries = official.MAX_RETRIES
                configuration.socket_options = None
                size = local.stat().st_size
                upload = (
                    official.upload_small_file
                    if size <= official.CHUNK_SIZE
                    else official.upload_large_file
                )
                result = upload(str(local), target, size, token, configuration)
            finally:
                naming.reset(flag)
            # Upstream ApiException strings may contain a credential-bearing URL.
            return json.loads(redact(json.dumps(result, ensure_ascii=False), token))
        except Exception:
            return {
                "status": "error",
                "message": "Upload failed. Check authorization, destination and network; no sensitive diagnostic is returned.",
            }

    authorization.start_monitor()
    try:
        mcp.run(transport="stdio")
    finally:
        authorization.stop.set()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Baidu local MCP could not start. Check installation and authorization.",
            file=sys.stderr,
        )
        sys.exit(1)
