"""Publication must preserve the last good snapshot on failed/partial sources."""
from datetime import datetime, timezone
from contextlib import nullcontext
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import ais
import collector
import data_store
import snapshot_store
import snapshot_update


class SnapshotUpdateTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.original = self.directory / "original.duckdb"
        shutil.copy2(snapshot_update.DATABASE, self.original)
        self.candidate = self.directory / "candidate.duckdb"
        self.now = datetime.now(timezone.utc)

    def response(self, *args, **kwargs):
        value = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [53.0, 26.0]},
            "properties": {"kind": "vessel", "mmsi": 123456789,
                           "seen": self.now.isoformat(), "source": "snapshot-test", "type": 70},
        }]}
        return io.BytesIO(json.dumps(value).encode())

    def ports(self, **kwargs):
        self.assertTrue(kwargs["strict"])
        self.assertTrue(kwargs["force"])
        self.assertTrue(kwargs["include_history"])
        for kind, pid in (("ports", "port105"), ("chokepoints", "chokepoint1")):
            data_store.save_portwatch(kind, [{"portid": pid, "date": self.now.date().isoformat()}], "test")
        return {"status": "ok"}

    def test_success_accumulates_history_and_ports_run_once_per_utc_day(self):
        original_digest = hashlib.sha256(self.original.read_bytes()).hexdigest()
        with patch("ais.urlopen", side_effect=self.response), \
             patch("collector.collect_portwatch_run", side_effect=self.ports) as ports:
            first = snapshot_update.collect_candidate(self.original, self.candidate, now=self.now)
            second = self.directory / "second.duckdb"
            result = snapshot_update.collect_candidate(self.candidate, second, now=self.now)
        self.assertEqual(ports.call_count, 1)
        self.assertTrue(first["portwatch_updated"])
        self.assertFalse(result["portwatch_updated"])
        self.assertGreater(first["after"]["counts"]["ais_reports"], first["before"]["counts"]["ais_reports"])
        self.assertGreaterEqual(result["after"]["counts"]["portwatch_daily"], first["after"]["counts"]["portwatch_daily"])
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(), original_digest)

    def test_failed_source_does_not_change_published_file(self):
        digest = hashlib.sha256(self.original.read_bytes()).hexdigest()
        with patch("ais.urlopen", side_effect=TimeoutError("offline")):
            with self.assertRaisesRegex(RuntimeError, "船位采集未完整成功"):
                snapshot_update.collect_candidate(self.original, self.candidate, now=self.now)
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(), digest)

    def test_portwatch_error_is_reported_to_scheduler(self):
        with patch("collector.collect_portwatch", side_effect=TimeoutError("offline")), \
             patch.dict(os.environ, {"MONITORING_DB_PATH": str(self.candidate), "MONITORING_READ_ONLY": "false"}):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                collector.collect_portwatch_run(strict=True)

    def test_remote_advance_during_collection_never_replaces_or_pushes_database(self):
        digest = hashlib.sha256(self.original.read_bytes()).hexdigest()
        remote_reads = []

        def fake_git(*args):
            if args == ("branch", "--show-current"):
                return "main"
            if args == ("rev-parse", "HEAD"):
                return "base"
            if args == ("rev-parse", "origin/main"):
                remote_reads.append(True)
                return "base" if len(remote_reads) == 1 else "advanced"
            return ""

        def fake_collect(original, candidate, **kwargs):
            candidate.write_bytes(b"new candidate")
            return {}

        with patch("snapshot_update.exclusive_update", return_value=nullcontext()), \
             patch("snapshot_update.DATABASE", self.original), \
             patch("snapshot_update.git", side_effect=fake_git) as git, \
             patch("snapshot_update.collect_candidate", side_effect=fake_collect):
            with self.assertRaisesRegex(RuntimeError, "main 已变化"):
                snapshot_update.run(publish=True)
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(), digest)
        self.assertFalse(any(call.args[0] in ("add", "commit", "push") for call in git.call_args_list))


class LfsMaterializationTest(unittest.TestCase):
    def test_pointer_download_is_verified_and_cached(self):
        payload = b"01234567DUCK" + b"snapshot-test-verified"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            pointer = Path(temporary) / "pointer.duckdb"
            pointer.write_text(f"version https://git-lfs.github.com/spec/v1\noid sha256:{digest}\nsize {len(payload)}\n")
            with patch("snapshot_store.tempfile.gettempdir", return_value=temporary), \
                 patch("snapshot_store.urlopen", return_value=io.BytesIO(payload)) as upstream:
                resolved = snapshot_store.materialize(pointer)
                self.assertEqual(resolved.read_bytes(), payload)
                self.assertEqual(snapshot_store.materialize(pointer), resolved)
                self.assertEqual(upstream.call_count, 1)
            self.assertTrue(pointer.read_text().startswith("version https://git-lfs"))

    def test_invalid_download_never_becomes_a_database(self):
        payload = b"01234567DUCK" + b"expected"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            pointer = Path(temporary) / "pointer.duckdb"
            pointer.write_text(f"version https://git-lfs.github.com/spec/v1\noid sha256:{digest}\nsize {len(payload)}\n")
            with patch("snapshot_store.tempfile.gettempdir", return_value=temporary), \
                 patch("snapshot_store.urlopen", return_value=io.BytesIO(b"invalid")):
                with self.assertRaisesRegex(ValueError, "SHA256"):
                    snapshot_store.materialize(pointer)
            self.assertFalse(list((Path(temporary) / "oil-field-map-snapshots").glob("*.duckdb")))


if __name__ == "__main__":
    unittest.main()
