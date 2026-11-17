"""Independent mutations of the complete-study evidence boundary."""
from copy import deepcopy
import unittest

from scripts.check_native_training_studies import (
    EXPECTED_WIRES, FIRST_IMAGE, SECOND_IMAGE, verify_observation,
)


def observation(target):
    # Fixed fixture dimensions and image identities from preserved replay evidence.
    from tests.virtual_dyadic_sweep_capture import sweep_stream_contract
    retained = "0" * 64
    wire = EXPECTED_WIRES[target]
    return {
        "status": "exited", "actual_exit_observed": True, "returncode": 0,
        "failures": [], "automatic_retries": 0,
        "streams": [
            {"observed_bytes": 50507464, "saved_bytes": 3103848,
             "wire_sha256": wire, "sha256": retained},
            {"observed_bytes": 0, "saved_bytes": 0},
        ],
        "sweep_capture": {
            "contract": sweep_stream_contract(compact_wire=True),
            "wire_sha256": wire, "retained_sha256": retained,
            "frames": [
                {"sweep": 1, "slot": 1, "bytes": 23701776, "sha256": FIRST_IMAGE},
                {"sweep": 2, "slot": 0, "bytes": 23701776, "sha256": SECOND_IMAGE},
            ],
        },
    }


class StudyObservationTests(unittest.TestCase):
    def test_all_five_preserved_wire_identities(self):
        self.assertEqual(len(EXPECTED_WIRES), 5)
        for target in EXPECTED_WIRES:
            with self.subTest(target=target):
                self.assertEqual(verify_observation(observation(target), target)["target"], target)

    def test_foreign_profile_and_unknown_target_reject(self):
        target = "virtual-dyadic-training"
        with self.assertRaises(ValueError):
            verify_observation(observation(target), "virtual-dyadic-training-mixed-policy-cache")
        with self.assertRaises(ValueError):
            verify_observation(observation(target), "virtual-dyadic-training-future")

    def test_failed_unobserved_or_retried_process_rejects(self):
        target = "virtual-dyadic-training"
        for key, value in (
            ("status", "timeout"), ("returncode", 1), ("returncode", False),
            ("actual_exit_observed", False), ("automatic_retries", 1),
            ("automatic_retries", False), ("failures", ["stdout_limit"]),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                record = observation(target)
                record[key] = value
                verify_observation(record, target)

    def test_truncated_extra_or_error_stream_rejects(self):
        target = "virtual-dyadic-training"
        for index, key, value in (
            (0, "observed_bytes", 50507463), (0, "observed_bytes", 50507465),
            (0, "saved_bytes", 3103847), (0, "wire_sha256", "f" * 64),
            (1, "observed_bytes", 1), (1, "saved_bytes", 1),
        ):
            with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                record = observation(target)
                record["streams"][index][key] = value
                verify_observation(record, target)

    def test_checkpoint_values_order_scale_and_types_reject(self):
        target = "virtual-dyadic-training"
        for key, value in (
            ("sweep", 2), ("slot", 0), ("bytes", 23701775),
            ("sha256", SECOND_IMAGE), ("sweep", True),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                record = observation(target)
                record["sweep_capture"]["frames"][0][key] = value
                verify_observation(record, target)
        record = observation(target)
        record["sweep_capture"]["frames"].reverse()
        with self.assertRaises(ValueError):
            verify_observation(record, target)

    def test_independent_transport_receipts_must_agree(self):
        target = "virtual-dyadic-training"
        for key in ("wire_sha256", "retained_sha256"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                record = observation(target)
                record["sweep_capture"][key] = "f" * 64
                verify_observation(record, target)
        record = observation(target)
        record["sweep_capture"]["contract"] = deepcopy(record["sweep_capture"]["contract"])
        record["sweep_capture"]["contract"]["frames"] = 3
        with self.assertRaises(ValueError):
            verify_observation(record, target)


if __name__ == "__main__":
    unittest.main()
