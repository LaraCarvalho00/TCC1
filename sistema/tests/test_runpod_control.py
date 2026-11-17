"""Protect the conditions under which the controller starts or removes a paid Pod."""
from unittest import TestCase
from unittest.mock import Mock, patch

from infra.runpod import control


class RunpodControlTest(TestCase):
    def setUp(self):
        self.record = {"run_id": "gh-1-1", "pod_name": "tcc-qwen-gh-1-1", "pod_id": "pod",
                       "state": "running", "started": 900, "deadline": 2000, "max_hourly": "1.42"}
        self.pod = {"id": "pod", "name": self.record["pod_name"], "status": "RUNNING",
                    "cost": 1.4, "gpu": {"id": "NVIDIA RTX A6000", "count": 2}}
        self.storage = Mock()
        self.storage.get_json.return_value = None

    def reconcile(self):
        with (patch.object(control, "matching_pod", return_value=self.pod),
              patch.object(control.time, "time", return_value=1000),
              patch.object(control, "set_pod_state", return_value="stopped") as transition,
              patch.object(control, "report")):
            control.reconcile(self.storage, "controls/gh-1-1.json", self.record)
        return transition

    def test_authorizes_only_allowed_hardware_and_price(self):
        transition = self.reconcile()
        transition.assert_not_called()
        self.storage.put_json.assert_any_call("runs/gh-1-1/start.json",
                                              {"pod_id": "pod", "hourly_rate": "1.4"})

    def test_above_price_limit_stops_and_preserves_volume(self):
        self.pod["cost"] = 1.43
        transition = self.reconcile()
        transition.assert_called_once_with(self.pod)
        self.assertEqual(self.record["state"], "stopped")

    def test_expired_run_stops_and_preserves_volume(self):
        self.record["deadline"] = 999
        transition = self.reconcile()
        transition.assert_called_once_with(self.pod)

    def test_terminates_only_when_all_expected_objects_exist(self):
        prefix = "runs/gh-1-1/"
        ids = [f"scenario-{i}" for i in range(80)]
        objects = [prefix + f"scenarios/{identifier}.tar.gz" for identifier in ids]
        status = {"state": "completed", "upload_complete": True, "completed": 80, "total": 80}
        store = {
            prefix + "status.json": status,
            prefix + "manifest.json": {"scenarios": [{"id": identifier} for identifier in ids]},
            prefix + "index.json": {"artifacts": [{"key": control.PREFIX + key} for key in objects]},
        }
        self.storage.get_json.side_effect = store.get
        self.storage.keys.return_value = objects[:-1]
        self.reconcile().assert_not_called()
        self.storage.keys.return_value = objects
        self.reconcile().assert_called_once_with(self.pod, terminate=True)
