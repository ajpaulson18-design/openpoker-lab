"""Independent finite-grid policy allocation controls; no training producer."""
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import os
import struct
import unittest
from tests.test_native_exact_reach import authenticate, sha
from tests.virtual_frozen_run_control import run_bounded_child

ROOT = Path(__file__).resolve().parents[1]
Q = 1 << 52


def allocation(weights, average=False):
    if average and any(value < 0 for value in weights):
        raise ValueError('average masses must be nonnegative')
    positive = [max(0,value) for value in weights]
    total = sum(positive)
    exact = [Fraction(value*Q,total) for value in positive] if total else [Fraction(Q,len(weights))]*len(weights)
    result = [value.numerator//value.denominator for value in exact]
    priority = sorted(range(len(weights)),key=lambda index: (-(exact[index]-result[index]),index))
    for index in priority[:Q-sum(result)]:
        result[index] += 1
    return result,total


class DyadicPolicyReferenceTests(unittest.TestCase):
    def test_exact_row_bound_ties_and_distinct_average_image(self):
        units,total = allocation([1,1,1],average=True)
        self.assertEqual(units,[Q//3+1,Q//3,Q//3])
        self.assertNotEqual(Fraction(units[0],Q),Fraction(1,3))
        self.assertTrue(all(abs(unit*total-Q)<total for unit in units))
        self.assertEqual(allocation([-1,0,2])[0],[0,0,Q])
        self.assertEqual(allocation([0,0,0])[1],0)
        with self.assertRaises(ValueError):
            allocation([-1,2],average=True)


@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_DYADIC_POLICY_EXE'),
                     'explicit source-built dyadic policy controls required')
class NativeDyadicPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = Path(os.environ['OPENPOKER_NATIVE_DYADIC_POLICY_EXE']).resolve()
        cls.identity = authenticate(cls.exe,ROOT,'dyadic-policy-controls')
        cls.temporary = None
        destination = os.environ.get('OPENPOKER_NATIVE_DYADIC_POLICY_CONTROL_DIR')
        if destination is None:
            cls.temporary = TemporaryDirectory()
            destination = cls.temporary.name
        cls.output = Path(destination)
        expected = cls.identity[1]['executable_sha256']
        before = sha(cls.exe)
        if before != expected:
            raise AssertionError('policy executable differs before launch')
        cls.observed = run_bounded_child([str(cls.exe)],b'',cls.output,stdout_limit=2100000)
        after = sha(cls.exe)
        (cls.output/'native-identity.json').write_text(json.dumps({'expected_sha256':expected,
            'before_sha256':before,'after_sha256':after,
            'manifest_sha256':hashlib.sha256(cls.identity[0]).hexdigest()})+'\n')
        if after != expected or cls.observed['status'] != 'exited' or cls.observed['returncode'] != 0:
            raise AssertionError('policy controls child failed: '+(cls.output/'stderr.bin').read_text())
        if (cls.output/'stderr.bin').read_bytes():
            raise AssertionError('unexpected policy control stderr')
        cls.lines = (cls.output/'stdout.bin').read_text(encoding='ascii').splitlines()

    @classmethod
    def tearDownClass(cls):
        if authenticate(cls.exe,ROOT,'dyadic-policy-controls') != cls.identity:
            raise AssertionError('policy source/build drift during controls')
        if cls.temporary is not None:
            cls.temporary.cleanup()

    def test_all_360_images_exact_bounds_binary64_and_cumulative_owner(self):
        self.assertEqual(self.lines[0],'DYADIC_POLICY_V1 52 20')
        previous_work = 0
        kinds = [0,0]
        fallback = [0,0]
        tiny_positive_zero = False
        for index,line in enumerate(self.lines[1:361]):
            fields = line.split()
            self.assertEqual(fields[0],'ROW')
            number,kind,profile,count,uniform = map(int,fields[1:6])
            self.assertEqual(number,index)
            self.assertIn(kind,(0,1)); self.assertIn(profile,range(10)); self.assertIn(count,range(1,21))
            self.assertEqual(len(fields),13+3*count)
            triples = [fields[6+3*i:9+3*i] for i in range(count)]
            weights = [int(item[0],16) for item in triples]
            units = [int(item[1]) for item in triples]
            bits = [int(item[2],16) for item in triples]
            expected,total = allocation(weights,kind==1)
            self.assertEqual(units,expected,(kind,profile,count))
            self.assertEqual(sum(units),Q)
            self.assertEqual(bool(uniform),total==0)
            kinds[kind] += 1
            fallback[kind] += int(bool(uniform))
            for weight,unit,image in zip(weights,units,bits):
                self.assertGreaterEqual(unit,0); self.assertLessEqual(unit,Q)
                exact = Fraction(unit,Q)
                self.assertEqual(Fraction.from_float(float(exact)),exact)
                self.assertEqual(struct.unpack('>Q',struct.pack('>d',float(exact)))[0],image)
                if total:
                    self.assertLess(abs(unit*total-max(0,weight)*Q),total)
                    if weight <= 0:
                        self.assertEqual(unit,0)
                    if weight > 0 and unit == 0:
                        tiny_positive_zero = True
            self.assertEqual(fields[6+3*count],'META')
            work,rows,input_bits,forecast_bits,entries,payload = map(int,fields[7+3*count:])
            self.assertGreater(work,previous_work)
            self.assertLessEqual(work,500000000); self.assertEqual(rows,index+1)
            self.assertLessEqual(input_bits,65536); self.assertLessEqual(forecast_bits,65536)
            self.assertLessEqual(entries,2000000); self.assertLessEqual(payload,1<<30)
            previous_work = work
        self.assertEqual(kinds,[200,160])
        self.assertTrue(all(fallback))
        self.assertTrue(tiny_positive_zero)
        self.assertEqual(self.lines[361],f'END 360 {previous_work}')

    def test_rejected_rows_limits_and_cumulative_exhaustion(self):
        end = self.lines.index('GUARDS_END PASS')
        guards = self.lines[362:end]
        self.assertEqual(len(guards),24)
        for line in guards:
            fields = line.split()
            self.assertEqual(len(fields),3)
            self.assertEqual(fields[0],'GUARD')
            self.assertEqual(fields[2],'PASS',line)
        self.assertEqual(self.lines[end],'GUARDS_END PASS')
        self.assertTrue(self.observed['actual_exit_observed'])
        self.assertEqual(self.observed['automatic_retries'],0)

    def test_combined_division_matches_independent_fraction_oracle(self):
        rows=[line.split() for line in self.lines if line.startswith('COMBINED ')]
        self.assertEqual(len(rows),80)
        divisions=0
        for fields in rows:
            kind,profile,count,fallback=map(int,fields[1:5])
            self.assertIn(count,range(1,5))
            self.assertIn(profile,range(11))
            self.assertEqual(len(fields),5+2*count)
            values=[int(x,16) for x in fields[5::2]]
            positives=sum(value>0 for value in values)
            if positives>1:
                divisions+=positives
            units=list(map(int,fields[6::2]))
            expected,total=allocation(values,average=bool(kind))
            self.assertEqual(units,expected,(kind,profile,count))
            self.assertEqual(bool(fallback),not total)
            self.assertEqual(sum(units),Q)
        self.assertEqual(self.lines[-1],f'COMBINED_END 80 {divisions} PASS')
        for label in ('combined_width','combined_intermediate_width','combined_work'):
            self.assertIn('GUARD '+label+' PASS',self.lines)


if __name__ == '__main__':
    unittest.main()
