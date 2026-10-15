"""Resolve an immutable Git/LFS snapshot before the dashboard imports catalogs."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.request import Request, urlopen

import data_store

REPOSITORY = "BichengNiu/oil-field-map-demo"
_APP_INPUT_PATH = data_store.database_path()


def materialize(path: Path) -> Path:
    with path.open("rb") as handle:
        prefix = handle.read(512)
    if not prefix.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
        if prefix[8:12] != b"DUCK":
            raise ValueError("数据库快照文件无效")
        return path
    pointer = prefix.decode("ascii")
    match = re.fullmatch(r"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize (\d+)\n?", pointer)
    if not match:
        raise ValueError("Git LFS 指针格式无效")
    digest, size = match.group(1), int(match.group(2))
    directory = Path(tempfile.gettempdir()) / "oil-field-map-snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{digest}.duckdb"

    def valid(candidate):
        if not candidate.exists() or candidate.stat().st_size != size:
            return False
        checksum = hashlib.sha256()
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                checksum.update(chunk)
        return checksum.hexdigest() == digest

    if valid(destination):
        return destination
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=data_store.ROOT,
                            capture_output=True, text=True).stdout.strip()
    revision = commit if re.fullmatch(r"[0-9a-f]{40}", commit) else "main"
    request = Request(f"https://media.githubusercontent.com/media/{REPOSITORY}/{revision}/runtime/monitoring.duckdb",
                      headers={"User-Agent": "oil-field-map-demo/snapshot"})
    descriptor, temporary = tempfile.mkstemp(dir=directory, suffix=".download")
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as target, urlopen(request, timeout=60) as source:
            count = 0
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                count += len(chunk)
                if count > size:
                    raise ValueError("下载的数据库超过 LFS 声明大小")
                target.write(chunk)
        if not valid(temporary):
            raise ValueError("数据库快照大小或 SHA256 校验失败")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def configure_app_snapshot():
    path = materialize(_APP_INPUT_PATH)
    os.environ["MONITORING_DB_PATH"] = str(path)
    os.environ["MONITORING_READ_ONLY"] = "true"
