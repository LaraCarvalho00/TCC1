"""Cloud lifecycle decisions without AWS credentials or billable resources."""
from datetime import datetime, timedelta, timezone
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("cloud_control", Path(__file__).resolve().parents[2] / "infra/aws/control.py")
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)
NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


class CloudControlTest(unittest.TestCase):
    def payload(self, **inputs):
        return control.payload(inputs, run_id="gh-123-1", bucket="results", region="us-east-1", now=NOW)

    def test_matrix_has_40000_new_generations_and_absolute_deadline(self):
        data = self.payload()
        self.assertEqual((data["nodes"], data["rounds"], data["planned_scenarios"], data["planned_generations"]),
                         (50, 50, 16, 40000))
        self.assertEqual(data["deadline_epoch"], int((NOW + timedelta(hours=72)).timestamp()))
        self.assertEqual((data["inference_layout"], data["model_instances"], data["gpu_count"]), ("per_node", 50, 8))
        self.assertNotIn("workers", data)

    def test_rejects_small_host_before_any_aws_call(self):
        with self.assertRaisesRegex(ValueError, "VRAM"):
            self.payload(instance_type="g6e.12xlarge")

    def test_custom_counts_and_both_scores_probabilities(self):
        data = self.payload(mode="custom", honest_nodes=12, malicious_nodes=8, rounds=6, max_hours=6)
        self.assertEqual((data["nodes"], data["planned_scenarios"], data["planned_generations"]), (20, 4, 480))

    def test_reject_bad_or_unbounded_dispatch_input(self):
        for bad in ({"max_hours": 0}, {"max_hours": 169}, {"seed": -1}, {"rounds": 51},
                    {"honest_nodes": "$(id)"}, {"mode": "custom", "honest_nodes": 2, "malicious_nodes": 1},
                    {"mode": "custom", "honest_nodes": 0, "malicious_nodes": 50},
                    {"mode": "unknown"}, {"rounds": True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.payload(**bad)

    def test_dont_reap_live_run_or_race_provisioning(self):
        record = self.payload()
        self.assertFalse(control.should_cleanup(record, {"state": "running"}, ["running"], now=NOW))
        self.assertFalse(control.should_cleanup(record, None, [], now=NOW + timedelta(minutes=20)))
        self.assertFalse(control.should_cleanup(record, {"state": "completed", "upload_complete": False}, ["running"], now=NOW))

    def test_reap_after_verified_upload_or_expiry_or_host_failure(self):
        record = self.payload()
        self.assertTrue(control.should_cleanup(record, {"state": "completed", "upload_complete": True}, ["running"], now=NOW))
        self.assertTrue(control.should_cleanup(record, {"state": "running"}, ["running"], now=NOW + timedelta(hours=73)))
        self.assertTrue(control.should_cleanup(record, None, ["terminated"], now=NOW + timedelta(hours=2)))
        self.assertTrue(control.should_cleanup(record, None, [], now=NOW + timedelta(hours=2)))
        self.assertTrue(control.should_cleanup(record, None, ["running"], now=NOW, force=True))

    def test_recovery_archive_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "source.tar.gz"
            with tarfile.open(archive, "w:gz") as stream:
                member = tarfile.TarInfo("../escape")
                member.size = 1
                stream.addfile(member, io.BytesIO(b"x"))
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                control.extract_source(archive, root / "extract")

    def test_cleanup_terminates_exact_host_even_when_source_download_fails(self):
        record = {**self.payload(), "project_name": "distributed-ai"}
        session = mock.Mock()
        ec2 = session.client.return_value
        ec2.describe_instances.return_value = {"Reservations": [{"Instances": [
            {"InstanceId": "i-owned-run", "State": {"Name": "running"}},
            {"InstanceId": "i-already-stopped", "State": {"Name": "terminated"}},
        ]}]}
        session.client.return_value.download_file.side_effect = RuntimeError("S3 unavailable")
        with mock.patch.object(control, "get_json", return_value=None), \
             mock.patch.object(control, "put_json") as publish:
            with self.assertRaisesRegex(RuntimeError, "S3 unavailable"):
                control.cleanup_one(session, record, force=True)
        ec2.terminate_instances.assert_called_once_with(InstanceIds=["i-owned-run"])
        publish.assert_not_called()
        filters = ec2.describe_instances.call_args.kwargs["Filters"]
        self.assertEqual(filters, [{"Name": "tag:Project", "Values": ["distributed-ai"]},
                                   {"Name": "tag:RunId", "Values": ["gh-123-1"]}])


if __name__ == "__main__":
    unittest.main()
