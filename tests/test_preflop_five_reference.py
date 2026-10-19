"""Boundary gates for a fixed independent physical-count research reference."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import validate_preflop_five_reference as reference
from scripts import build_preflop_five_reference as builder

class FiveReferenceTests(unittest.TestCase):
    def test_fixed_source_pair_labels_and_integer_call_census_are_mandatory(self):
        # Synthetic complete totals exercise protocol validation only.
        data={'schema_version':1,'reference':'preflop-five-card-basis-v1',
              'pairs':[{'sb_ids':[49,51],'bb_ids':list(bb),'wins':1000000,'ties':12304,
                        'losses':700000,'boards':1712304} for bb in ((45,47),(44,45),(44,46))],
              'boards_total':5136912,'five_card_rank_calls':215750304,'seven_card_rank_calls':10273824}
        rows=reference.verify_count_result(data)
        self.assertEqual([(x['sb_hand'],x['bb_hand']) for x in rows],list(reference.PAIRS))
        for mutate in (lambda x:x.update(five_card_rank_calls=215750303),
                       lambda x:x.update(schema_version=True),
                       lambda x:x['pairs'][1].update(bb_ids=[45,47]),
                       lambda x:x['pairs'][0].update(wins=True),
                       lambda x:x['pairs'][2].update(ties=12305)):
            bad=deepcopy(data);mutate(bad)
            with self.assertRaises(ValueError):reference.verify_count_result(bad)

    def test_truncated_dump_rejects_before_python_rank_oracle(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'short.bin';path.write_bytes(b'\0'*6)
            with patch.object(reference,'_five_rank',side_effect=AssertionError('ranked short dump')):
                with self.assertRaisesRegex(ValueError,'exactly'):reference.validate_five_dump(path)

    def test_dirty_source_blocks_executable_and_oracle_calls_but_saves_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'observation'
            with (patch.object(reference,'snapshot',return_value={'status':['dirty']}),
                  patch.object(reference,'backend') as executable,
                  patch.object(reference,'plan_preflop_equities') as planned):
                path,report=reference.run('unused','unused',output)
            executable.assert_not_called();planned.assert_not_called()
            self.assertEqual(report['status'],'error')
            self.assertEqual(json.loads(path.read_bytes())['errors'],report['errors'])
            with self.assertRaisesRegex(ValueError,'new output directory'):
                reference.run('unused','unused',output)

    def test_build_refuses_checkout_and_never_overwrites_earlier_data(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            builder.build(builder.ROOT/'forbidden-reference-build')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);(path/'existing.txt').write_text('retain')
            with patch.object(builder.shutil,'which',return_value='compiler'):
                with self.assertRaisesRegex(ValueError,'empty'):builder.build(path)
            self.assertEqual((path/'existing.txt').read_text(),'retain')

    def test_frozen_spec_matches_literal_checksum(self):
        spec=json.loads(reference.SPEC_PATH.read_bytes())
        self.assertEqual(reference.checksum(spec),reference.SPEC_SHA256)
        self.assertEqual(spec['full_board_reference']['five_card_rank_calls'],1712304*3*2*21)
        self.assertEqual(spec['five_card_conformance']['dump_bytes'],2598960*6)
