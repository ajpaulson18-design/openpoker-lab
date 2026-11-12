"""Protect the coupled work proof and fail closed on changed event realization."""
import copy
import json
from pathlib import Path
import unittest
from zipfile import ZipFile
from scripts.run_virtual_dyadic_compact_cohort import legacy_admission, verify_factored_execution, FACTORED_COUNTS, FACTORED_WORK

ROOT=Path(__file__).resolve().parents[1]

class FactoredReceiptTests(unittest.TestCase):
    def admission(self):
        with ZipFile(ROOT/"benchmarks/results/native-dyadic-compact-wire-v1/verification.zip") as bundle:
            record=json.loads(bundle.read("cohort/admission.json"))
        record.update(factored_execution=True,factored_metadata_work=FACTORED_WORK,
            factored_composed_work=record["compact_composed_work"]+FACTORED_WORK,
            factored_composed_entries=record["compact_composed_entries"]+8192,
            factored_composed_payload_bits=record["compact_composed_payload_bits"]+524288)
        return record

    def test_composed_budget_and_profile_identity(self):
        record=self.admission()
        self.assertEqual(record["factored_composed_work"],2_137_373_778)
        legacy_admission(record,factored=True)
        with self.assertRaises(ValueError):legacy_admission(record)
        for key in ("factored_metadata_work","factored_composed_work","factored_composed_entries","factored_composed_payload_bits"):
            bad=copy.deepcopy(record);bad[key]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):legacy_admission(bad,factored=True)

    def test_equal_fee_substitutions_do_not_preserve_proof(self):
        record={**FACTORED_COUNTS,"work":FACTORED_WORK,"packed_additions":1,"packed_subtractions":1,
            "packed_clipped":0,"packed_target_words_read":5_925_444,"packed_target_words_written":5_925_444,
            "implicit_zero_bits":1,"maximum_coefficient_bits":645,"maximum_shift":644}
        verify_factored_execution(record,self.admission())
        for key in FACTORED_COUNTS:
            bad=dict(record);bad[key]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):verify_factored_execution(bad,self.admission())
        bad=dict(record);bad["scales"]-=1;bad["additions"]+=1
        with self.assertRaises(ValueError):verify_factored_execution(bad,self.admission())
        for key,value in (("work",True),("unknown",0),("packed_target_words_written",0)):
            bad=dict(record);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):verify_factored_execution(bad,self.admission())

if __name__=="__main__":unittest.main()
