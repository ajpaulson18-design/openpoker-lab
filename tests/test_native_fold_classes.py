"""Source-authenticated native fold-class and coupled-trainer controls."""
import subprocess
import unittest

from tests.test_native_active_frames import _AuthenticatedControls


class NativeFoldClassControls(_AuthenticatedControls, unittest.TestCase):
    target = "fold-classes"
    environment = "OPENPOKER_NATIVE_FOLD_CLASS_CONTROLS_EXE"
    prefix = "opl-native-fold-classes-"

    def test_exact_vectors_resource_guards_and_coupled_policy_bits(self):
        result = subprocess.run([str(self.executable)], capture_output=True, timeout=180)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode("utf-8", "replace"))
        self.assertIn(b"ALL FOLD CLASS CONTROLS PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()
