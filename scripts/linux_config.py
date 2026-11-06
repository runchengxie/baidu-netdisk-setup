"""Explicit Linux settings and permission-restricted private JSON persistence."""

import json
import os
from pathlib import Path
import stat
import tempfile
import tomllib


def resolve_roots(explicit=None, environment=None, workspace=None):
    explicit = explicit or {}
    environment = os.environ if environment is None else environment
    configured = {}
    if workspace:
        with Path(workspace).open("rb") as stream:
            configured = tomllib.load(stream).get("roots", {})
    result = {}
    for name in ("CODE_ROOT", "DATA_ROOT", "CONFIG_ROOT"):
        value = explicit.get(name) or environment.get(name) or configured.get(name)
        if not isinstance(value, str) or not Path(value).expanduser().is_absolute():
            raise RuntimeError("Explicit absolute workspace roots are required")
        result[name] = Path(value).expanduser()
    return result


def private_path(path, root):
    path, root = Path(path), Path(root)
    if (
        not path.is_absolute()
        or not root.is_absolute()
        or ".." in path.parts
        or ".." in root.parts
    ):
        raise RuntimeError("Private path must be absolute")
    if path == root or not path.is_relative_to(root):
        raise RuntimeError("Private file must be within deployment directory")
    for item in (path, *path.parents):
        if item.is_symlink():
            raise RuntimeError("Symlink private paths are unsupported")
        if (item / ".git").exists() and item != Path.home():
            raise RuntimeError("Private files must be outside source repositories")
    for directory in (
        root,
        *[p for p in path.parents if p != root and p.is_relative_to(root)],
    ):
        info = directory.stat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise RuntimeError("Private directories require owner-only permissions")
    return path


def read_private_json(path, root):
    path = private_path(path, root)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise RuntimeError("Private files require owner-only permissions")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = None
            return json.load(stream)
    finally:
        if fd is not None:
            os.close(fd)


def fsync_directory(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_private_json(path, value, root, *, replace=True):
    path = private_path(path, root)
    if path.exists():
        read_private_json(path, root)
        if not replace:
            raise RuntimeError("Existing private file preserved")
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
            os.unlink(temporary)
        fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_settings(path):
    path = Path(path).absolute()
    root = path.parent
    value = read_private_json(path, root)
    if (
        not isinstance(value, dict)
        or value.get("platform") != "linux"
        or value.get("deploymentRoot") != str(root)
    ):
        raise RuntimeError("Explicit Linux installation settings required")
    for key in ("tokenFile", "secretFile"):
        private_path(value[key], root)
    for key in ("python", "officialDir", "bridge"):
        if not isinstance(value.get(key), str) or not Path(value[key]).is_absolute():
            raise RuntimeError("Invalid runtime configuration")
    return value
