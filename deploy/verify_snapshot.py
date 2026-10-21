"""Verify the database can be downloaded from GitHub at the published commit."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify():
    commit = git("rev-parse", "HEAD")
    remote = git("ls-remote", "origin", "refs/heads/main").split()[0]
    if remote != commit:
        raise RuntimeError("Remote main changed; cannot certify this checkout as latest")
    pointer = git("show", f"{commit}:runtime/monitoring.duckdb")
    match = re.fullmatch(
        r"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize (\d+)", pointer)
    if not match:
        raise RuntimeError("Published database is not a valid LFS pointer")
    expected_hash, expected_size = match.group(1), int(match.group(2))
    request = Request(
        f"https://media.githubusercontent.com/media/BichengNiu/oil-field-map-demo/{commit}/runtime/monitoring.duckdb",
        headers={"User-Agent": "oil-field-map-demo/publication-verification"})
    digest, size = hashlib.sha256(), 0
    with urlopen(request, timeout=120) as response:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            size += len(chunk)
            if size > expected_size:
                raise RuntimeError("Remote LFS object exceeds declared size")
            digest.update(chunk)
    if size != expected_size or digest.hexdigest() != expected_hash:
        raise RuntimeError("Remote LFS object failed size/SHA256 verification")
    print(json.dumps({"status": "verified", "commit": commit,
                      "database_sha256": expected_hash, "bytes": size}))


if __name__ == "__main__":
    verify()
