"""Independent Python-integer oracle for source-built policy division."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.test_native_exact_reach import authenticate, sha
from tests.virtual_frozen_run_control import run_bounded_child

ROOT=Path(__file__).resolve().parents[1]
ENV="OPENPOKER_NATIVE_DYADIC_POLICY_DIVISION_EXE"

@unittest.skipUnless(os.environ.get(ENV),"source-built policy division controls required")
class PolicyDivisionTests(unittest.TestCase):
    def test_cpp_differentials_and_independent_python_vectors(self):
        exe=Path(os.environ[ENV]).resolve()
        before=authenticate(exe,ROOT,"dyadic-policy-division-controls")
        with TemporaryDirectory() as folder:
            output=Path(folder)/"division"
            observed=run_bounded_child([str(exe)],b"",output,stdout_limit=131072)
            self.assertEqual((observed["status"],observed["returncode"],observed["actual_exit_observed"]),
                             ("exited",0,True))
            self.assertEqual((output/"stderr.bin").read_bytes(),b"")
            lines=(output/"stdout.bin").read_text(encoding="ascii").splitlines()
            self.assertEqual(lines[-1],"grid division controls passed")
            self.assertEqual(len(lines),97)
            for line in lines[:-1]:
                tag,weight,total,quotient,remainder=line.split("\t")
                self.assertEqual(tag,"vector")
                weight,total,quotient,remainder=map(int,(weight,total,quotient,remainder))
                self.assertTrue(0<=weight<=total and 0<total and total.bit_length()<=704)
                self.assertEqual((quotient,remainder),divmod(weight<<52,total))
                self.assertLessEqual(quotient,1<<52)
                self.assertLess(remainder,total)
        self.assertEqual(sha(exe),before[1]["executable_sha256"])
        self.assertEqual(authenticate(exe,ROOT,"dyadic-policy-division-controls"),before)

if __name__=="__main__":
    unittest.main()

