from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from copy import deepcopy
import hashlib
import json
import sys
import unittest
from scripts import run_native_exact_reach_conformance as controller


class ExactReachConformanceGuards(unittest.TestCase):
    def test_plain_entry_rejects_before_claim_or_build(self):
        with patch.object(sys, '_opl_source_bootstrap', None, create=True):
            with patch.object(controller, 'RunClaim') as claim, patch.object(controller, 'build') as build:
                with self.assertRaisesRegex(ValueError, 'source-only bootstrap required'):
                    controller.complete(None, 'a'*40, None)
                claim.assert_not_called()
                build.assert_not_called()

    def test_optimized_parent_rejects_before_source_or_claim(self):
        with patch.object(controller, 'require_source_bootstrap', return_value={'interpreter': {'optimize': 1}}):
            with patch.object(controller, '_git') as git, patch.object(controller, 'RunClaim') as claim:
                with self.assertRaisesRegex(ValueError, 'normal parent mode'):
                    controller.complete(None, 'a'*40, None)
                git.assert_not_called()
                claim.assert_not_called()

    def test_wrong_candidate_head_rejects_before_claim_or_build(self):
        with patch.object(controller, 'require_source_bootstrap', return_value={'interpreter': {'optimize': 0}}):
            with patch.object(controller, '_git', return_value=('b'*40+'\n').encode()):
                with patch.object(controller, 'RunClaim') as claim, patch.object(controller, 'build') as build:
                    with self.assertRaisesRegex(ValueError, 'candidate HEAD differs'):
                        controller.complete(None, 'a'*40, None)
                    claim.assert_not_called()
                    build.assert_not_called()

    def test_compiled_source_drift_rejects_before_binary_or_header_admission(self):
        target = 'full-deck-chance'
        required = {*controller.TARGETS[target][1], 'scripts/build_native_exact_four_street.py',
                    'third_party/boost-multiprecision-1.92.0/manifest.json',
                    'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt',
                    'third_party/boost-multiprecision-1.92.0/headers.zip'}
        source = {'files': {name: {'raw_sha256': 'a'*64} for name in required}}
        hashes = {name: 'a'*64 for name in required}
        for altered in ({**hashes, 'native/full_deck_public_chance.hpp': 'b'*64},
                        {name: value for name, value in hashes.items() if name != 'native/full_deck_public_chance.hpp'},
                        {**hashes, 'unexpected.hpp': 'a'*64}):
            manifest = {'contract': 'native-exact-build-v1', 'target': target, 'source_sha256': altered}
            with self.subTest(altered=altered):
                with patch.object(controller, 'sha', side_effect=AssertionError('binary/hash phase entered')):
                    with self.assertRaises(ValueError):
                        controller.bind_build(manifest, source, target, None, None)

    def test_child_receipt_requires_exact_executed_bytes_runtime_and_first_stage(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root/'receipt.json'
            bootstrap = 'scripts/run_virtual_frozen_source_only.py'
            builder = 'scripts/build_native_exact_four_street.py'
            source = {'files': {bootstrap: {'raw_sha256': 'a'*64}, builder: {'raw_sha256': 'b'*64}}}
            runtime = {'optimize': 0, 'path': 'fixed-runtime', 'sha256': 'c'*64,
                       'version': 'fixture', 'isolated': 1, 'no_site': 1, 'dont_write_bytecode': True}
            receipt = {'root': str(root), 'entry_module': 'scripts.build_native_exact_four_street',
                       'version': 'project-source-only-bootstrap-v1',
                       'initial_cache_scan': {'project_bytecode_files': 0},
                       'final_cache_scan': {'project_bytecode_files': 0},
                       'compiled': {bootstrap: 'a'*64, builder: 'b'*64}, 'interpreter': runtime,
                       'trusted_first_stage': {'bootstrap_path': str(root/bootstrap),
                           'bootstrap_sha256': 'a'*64,
                           'command_sha256': hashlib.sha256(controller.FIRST_STAGE.encode()).hexdigest()}}
            def write(value):
                path.write_text(json.dumps(value))
            with patch.object(controller, 'require_source_bootstrap', return_value={'interpreter': runtime}):
                write(receipt)
                self.assertEqual(controller.child_bootstrap(path, root, source,
                    'scripts.build_native_exact_four_street'), receipt)
                for field, value in [('compiled', {bootstrap: 'a'*64}),
                                     ('compiled', {bootstrap: 'a'*64, builder: 'd'*64}),
                                     ('trusted_first_stage', {}), ('interpreter', {**runtime, 'optimize': 1}),
                                     ('final_cache_scan', {'project_bytecode_files': 1})]:
                    with self.subTest(field=field, value=value):
                        changed = deepcopy(receipt)
                        changed[field] = value
                        write(changed)
                        with self.assertRaises(ValueError):
                            controller.child_bootstrap(path, root, source,
                                'scripts.build_native_exact_four_street')


if __name__ == '__main__':
    unittest.main()
