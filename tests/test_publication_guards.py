"""A successful push must preserve LFS hooks and serve the exact database bytes."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_snapshot", ROOT / "deploy/verify_snapshot.py")
verify_snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_snapshot)


class PublicationGuardsTest(unittest.TestCase):
    def test_remote_download_must_match_pointer_hash_even_when_size_matches(self):
        payload = b"valid database bytes"
        digest = hashlib.sha256(payload).hexdigest()
        pointer = f"version https://git-lfs.github.com/spec/v1\noid sha256:{digest}\nsize {len(payload)}"
        with patch.object(verify_snapshot, "git", side_effect=["a" * 40, "a" * 40 + " refs/heads/main", pointer]), \
             patch.object(verify_snapshot, "urlopen", return_value=io.BytesIO(b"x" * len(payload))):
            with self.assertRaisesRegex(RuntimeError, "SHA256"):
                verify_snapshot.verify()

    def test_remote_branch_advance_cannot_be_reported_as_latest(self):
        with patch.object(verify_snapshot, "git", side_effect=["a" * 40, "b" * 40 + " refs/heads/main"]), \
             patch.object(verify_snapshot, "urlopen") as download:
            with self.assertRaisesRegex(RuntimeError, "main changed"):
                verify_snapshot.verify()
            download.assert_not_called()

    def test_main_download_verified(self):
        payload = b"valid database bytes"
        digest = hashlib.sha256(payload).hexdigest()
        pointer = f"version https://git-lfs.github.com/spec/v1\noid sha256:{digest}\nsize {len(payload)}"
        with patch.object(verify_snapshot, "git", side_effect=["a" * 40, "a" * 40 + " refs/heads/main", pointer]), \
             patch.object(verify_snapshot, "urlopen", return_value=io.BytesIO(payload)), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            verify_snapshot.verify()
            self.assertIn('"status": "verified"', output.getvalue())

    def test_hooks_block_other_branches_and_preserve_lfs_push_input(self):
        # Mock git; never create another actual branch, even for tests.
        with tempfile.TemporaryDirectory() as directory:
            fake_git = Path(directory) / "git"
            fake_git.write_text('#!/bin/sh\nif [ "$1" = branch ]; then echo "$TEST_BRANCH"; else cat > "$TEST_LFS_INPUT"; fi\n')
            fake_git.chmod(0o755)
            lfs_input = Path(directory) / "lfs-input"
            env = dict(os.environ, PATH=directory + os.pathsep + os.environ["PATH"],
                       TEST_BRANCH="work", TEST_LFS_INPUT=str(lfs_input))
            result = subprocess.run(["bash", str(ROOT / "deploy/main-only-pre-commit")], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            env["TEST_BRANCH"] = "main"
            hook = ["bash", str(ROOT / "deploy/main-only-pre-push"), "origin", "mock-origin"]
            result = subprocess.run(hook, input="refs/heads/main a refs/heads/work b\n", text=True, env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(lfs_input.exists())
            updates = "refs/heads/main a refs/heads/main b\n"
            result = subprocess.run(hook, input=updates, text=True, env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(lfs_input.read_text(), updates)


if __name__ == "__main__":
    unittest.main()
