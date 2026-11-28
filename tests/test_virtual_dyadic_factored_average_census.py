"""Independent controls for average-width and parent-work evidence."""
from copy import deepcopy
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import unittest

from scripts.census_virtual_dyadic_factored_average import forecast_saving, grid, partition
from tests.test_native_dyadic_policy import allocation

ROOT=Path(__file__).resolve().parents[1]


class FactoredAverageCensusTests(unittest.TestCase):
    def test_independent_grid_matches_fraction_allocator(self):
        cases=[(0,0),(3,3),(1,2,3),(-1,7,7,0),(1<<600,3<<600,0)]
        rng=random.Random(731)
        for _ in range(96):
            cases.append(tuple(rng.randrange(-5,91)<<rng.randrange(0,150)
                               for _ in range(rng.randrange(2,5))))
        for row in cases:
            with self.subTest(row=row):
                self.assertEqual(grid(row),tuple(allocation(row)[0]))

    def test_rank_free_width_bounds(self):
        self.assertEqual(forecast_saving(10),
                         {"before":26064384,"after":23285828,"reduction":2778556})
        self.assertEqual(forecast_saving(11),
                         {"before":83548782,"after":74450085,"reduction":9098697})

    def test_parent_partition_rejects_changed_native_receipts(self):
        native=json.loads((ROOT/"benchmarks/results/native-dyadic-factored-average-v1/native-eleven-forecast.json").read_bytes())
        with TemporaryDirectory(dir=ROOT.parent) as directory:
            path=Path(directory)/"forecast.json"
            path.write_text(json.dumps(native))
            self.assertEqual(partition(path)["sum"],2308449784)
            for kind in ("route","paging","training"):
                changed=deepcopy(native)
                if kind=="route": changed["parent_work"][7]-=1
                elif kind=="paging": changed["parent_details"]["paging"]+=1
                else: changed["training_invocations"]=1
                path.write_text(json.dumps(changed))
                with self.subTest(kind=kind),self.assertRaises(ValueError):
                    partition(path)


if __name__=="__main__":
    unittest.main()

