"""Corrupt immutable saved observations, never launch the native producer."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import struct
from tempfile import TemporaryDirectory
import unittest

from scripts.replay_native_frozen_policy_state import relative_name,replay

ENV='OPENPOKER_NATIVE_FROZEN_POLICY_STATE_CONTROL_DIR'


class SourcePathTests(unittest.TestCase):
    def test_only_canonical_relative_source_paths(self):
        self.assertEqual(relative_name('native/example.hpp'),'native/example.hpp')
        for name in ('','../x','/x','C:/x','a\\b','a//b','a/./b',None):
            with self.subTest(name=name),self.assertRaises(ValueError):relative_name(name)


@unittest.skipUnless(os.environ.get(ENV),'saved native observations required')
class SavedReplayTests(unittest.TestCase):
    def test_saved_observations_and_corruptions_without_candidate_calls(self):
        original=Path(os.environ[ENV])
        self.assertEqual(replay(original)['candidate_calls'],0)
        for case in ('source-byte','source-membership','source-blob','false-exit','command','stream-hash','output-ordinal','input-partition'):
            with self.subTest(case=case),TemporaryDirectory() as temporary:
                directory=Path(temporary)/'evidence';directory.mkdir()
                shutil.copytree(original/'source',directory/'source')
                for name in ('source-identity.json','native-build-manifest.json','native-identity.json',
                             'uniform.input.bin','zero-skew.input.bin','uniform.command.json','zero-skew.command.json'):
                    shutil.copyfile(original/name,directory/name)
                for name in ('uniform','zero-skew'):shutil.copytree(original/name,directory/name)
                def mutate_json(name,operation):
                    path=directory/name;value=json.loads(path.read_bytes());operation(value)
                    path.write_text(json.dumps(value),encoding='utf-8')
                if case=='source-byte':
                    path=directory/'source/native/virtual_dyadic_state.hpp';path.write_bytes(path.read_bytes()+b' ')
                elif case=='source-membership':
                    mutate_json('source-identity.json',lambda x:x['raw_sha256'].pop('native/virtual_dyadic_state.hpp'))
                elif case=='source-blob':
                    mutate_json('source-identity.json',lambda x:x['committed_blobs'].__setitem__('native/virtual_dyadic_state.hpp','0'*40))
                elif case=='false-exit':
                    mutate_json('uniform/process.json',lambda x:x.__setitem__('actual_exit_observed',False))
                elif case=='command':
                    mutate_json('uniform.command.json',lambda x:x.__setitem__(0,'foreign-executable'))
                elif case=='stream-hash':
                    mutate_json('uniform/process.json',lambda x:x['streams'][0].__setitem__('sha256','0'*64))
                elif case=='output-ordinal':
                    path=directory/'uniform/stdout.bin';raw=bytearray(path.read_bytes())
                    struct.pack_into('<Q',raw,80,1);path.write_bytes(raw)
                    mutate_json('uniform/process.json',lambda x:x['streams'][0].__setitem__('sha256',sha256(raw).hexdigest()))
                else:
                    path=directory/'uniform.input.bin';raw=bytearray(path.read_bytes())
                    # Last grid unit: invalidate its exact Q52 partition while
                    # recomputing the transport identity, so math must reject.
                    struct.pack_into('<Q',raw,len(raw)-8,1+struct.unpack_from('<Q',raw,len(raw)-8)[0]);path.write_bytes(raw)
                    mutate_json('uniform/input-identity.json',lambda x:x.__setitem__('sha256',sha256(raw).hexdigest()))
                with self.assertRaises(ValueError):replay(directory)


if __name__=='__main__':unittest.main()
