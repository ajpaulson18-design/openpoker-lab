"""Historical source authentication and bounded saved-value controls."""
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.matrix_free_certificate_budget import Budget
from scripts.replay_frozen_grid_packet import (
    FROZEN_HEAD,ORACLE_SOURCES,authenticate_oracle,decode_json,rational,replay,
)


class HistoricalGridReplayTests(unittest.TestCase):
    def test_duplicate_json_and_byte_ceiling(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            decode_json(b'{"same":1,"same":2}')
        with self.assertRaisesRegex(ValueError,'ceiling'):
            decode_json(b' '*11,10)

    def test_saved_rational_canonical_and_exact(self):
        self.assertEqual(rational(['-17','8'],Budget()),Fraction(-17,8))
        for raw in (['2','4'],['+1','1'],['0','2'],['1','0'],[True,'1'],['1',str(1<<705)]):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                rational(raw,Budget())

    def test_saved_rational_is_guarded_before_large_operation(self):
        with self.assertRaisesRegex(ValueError,'limit exceeded'):
            rational([str((1<<400)-1),str(1<<400)],Budget({'created_bits':100}))

    def test_unrelated_sources_tolerated_executed_sources_rejected(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);hashes={}
            for name in ORACLE_SOURCES:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'original source\n');hashes[name]=sha256(path.read_bytes()).hexdigest()
            source={'head':FROZEN_HEAD,'files':hashes}
            first=authenticate_oracle(source,root)
            (root/'unrelated_later_source.py').write_text('this is never imported\n')
            self.assertEqual(authenticate_oracle(source,root),first)
            (root/ORACLE_SOURCES[0]).write_text('changed source\n')
            with self.assertRaises(ValueError):authenticate_oracle(source,root)

    def test_historical_revision_must_be_the_declared_pin(self):
        with self.assertRaisesRegex(ValueError,'unknown historical'):
            authenticate_oracle({'head':'0'*40,'files':{}})

    def test_foreign_packet_rejected_before_git_or_oracle(self):
        with TemporaryDirectory() as directory,self.assertRaisesRegex(ValueError,'pinned repository'):
            replay(Path(directory))


if __name__=='__main__':unittest.main()
