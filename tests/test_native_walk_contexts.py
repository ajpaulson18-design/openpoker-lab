"""Adversarial controls for saved wall-time context recounting."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.replay_native_walk_contexts import analyze, labels, replay

def alias(name):
    return {"name":name,"flags":["f"],"object":"fixture.obj"}

def fixture():
    return {
        "format":"owned-child-wall-contexts-v1","native_image_sha256":"a"*64,
        "image_size":0x4000,"raw_report_sha256":"b"*64,"map_sha256":"c"*64,
        "return_pc_adjusted_before_module_lookup":True,"interval_ms":20,
        "external_seed_samples":0,"unknown_seed_samples":0,
        "ranges":[
            {"begin_rva":0x1000,"end_rva":0x1100,"unwind_rva":0x3000,
             "aliases":[alias("?visit@?$Walk@fixture")]},
            {"begin_rva":0x1100,"end_rva":0x1200,"unwind_rva":0x3004,
             "aliases":[alias("??$contract@$0A@@PreparedPublicChance@prepared_public_chance@fixture")]},
            {"begin_rva":0x1200,"end_rva":0x1300,"unwind_rva":0x3008,
             "aliases":[alias("?terminal@?$Walk@fixture")]},
        ],
        "samples":[{"elapsed_ms":20,"seed_rva":0x1101,"native_return_rvas":[0x10ff,0x1201],
                    "external_return_frames":1,"unknown_return_frames":0,
                    "status":"partial_unwind","stop_reason":"fixture"}],
    }

class NativeWalkContextTests(unittest.TestCase):
    def test_template_contract_and_nested_contexts(self):
        r=analyze(fixture())
        self.assertEqual(r["samples"],1)
        self.assertEqual(r["nested_walk_context_counts"]["walk"],1)
        self.assertEqual(r["nested_walk_context_counts"]["chance_contract"],1)
        self.assertEqual(r["nested_walk_context_counts"]["terminal"],1)

    def test_both_contract_spellings_and_foreign_owner(self):
        for name in ("?contract@PreparedPublicChance@prepared_public_chance@fixture",
                     "??$contract@$0A@@PreparedPublicChance@prepared_public_chance@fixture"):
            self.assertEqual(labels([alias(name)]),{"chance_contract"})
        self.assertEqual(labels([alias("??$contract@$0A@@Foreign@fixture")]),set())

    def test_aliases_do_not_multiply_samples(self):
        r=fixture()
        r["ranges"][1]["aliases"]*=2
        self.assertEqual(analyze(r)["nested_walk_context_counts"]["chance_contract"],1)

    def test_exclusive_extent_and_pre_adjusted_return_boundary(self):
        r=fixture()
        r["samples"][0]["native_return_rvas"]=[0x1100]
        self.assertEqual(analyze(r)["walk_observations"],0)
        r["samples"][0]["native_return_rvas"]=[0x10ff]
        self.assertEqual(analyze(r)["walk_observations"],1)
        r["return_pc_adjusted_before_module_lookup"]=False
        with self.assertRaises(ValueError): analyze(r)

    def test_external_seed_keeps_caller_and_denominator(self):
        r=fixture()
        r["samples"][0]["seed_rva"]=None
        r["external_seed_samples"]=1
        got=analyze(r)
        self.assertEqual((got["samples"],got["walk_observations"],got["external_seed_samples"]),(1,1,1))
        r["unknown_seed_samples"]=1
        with self.assertRaises(ValueError): analyze(r)

    def test_overlap_order_and_typed_rva_reject(self):
        for kind in ("overlap","rva","time","frame_cap","schema"):
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                r=fixture()
                if kind=="overlap": r["ranges"][1]["begin_rva"]=0x10ff
                elif kind=="rva": r["samples"][0]["seed_rva"]=True
                elif kind=="time": r["samples"].append(deepcopy(r["samples"][0]));r["samples"][1]["elapsed_ms"]=19
                elif kind=="frame_cap": r["samples"][0]["external_return_frames"]=64
                else: r["samples"][0]["extra"]=0
                analyze(r)

    def test_unproven_native_gap_gets_no_nearest_label(self):
        r=fixture()
        r["samples"][0]["seed_rva"]=0x2000
        r["samples"][0]["native_return_rvas"]=[]
        got=analyze(r)
        self.assertEqual(got["walk_observations"],0)
        self.assertEqual(got["seed_without_tracked_label"],1)

    def test_saved_roundtrip_and_duplicate_key_rejection(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/"capture.json.gz"
            path.write_bytes(gzip.compress(json.dumps(fixture()).encode()))
            self.assertEqual(replay(path),analyze(fixture()))
            raw=json.dumps(fixture())[:-1]+', "interval_ms":20}'
            path.write_bytes(gzip.compress(raw.encode()))
            with self.assertRaises(ValueError): replay(path)

if __name__=="__main__":
    unittest.main()

