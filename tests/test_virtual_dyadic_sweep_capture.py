"""Exercise the streaming demultiplexer across pipe and epoch boundaries."""
import hashlib
import io
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.run_virtual_dyadic_training_cohort import require_exit, verify_sweep_capture
from tests import virtual_dyadic_sweep_capture as capture
from tests.virtual_frozen_run_control import run_bounded_dyadic_probe


class SweepCaptureTests(unittest.TestCase):
    def setUp(self):
        self.first_image = capture.MAGIC + b'abc'
        self.second_image = b'defghijklmn'
        self.first_header = capture.FRAME.pack(capture.MAGIC, 1, 1, 11)
        self.second_header = capture.FRAME.pack(capture.MAGIC, 2, 0, 11)
        self.retained = b'abccurrentother--done'
        self.wire = (b'abccurrent' + self.first_header + self.first_image + b'other--' +
                     self.second_header + self.second_image + b'done')
        self.enterContext(patch.multiple(capture, PRELUDE_BYTES=3, PROFILE_AND_ROOT_BYTES=7,
                         IMAGE_BYTES=11, RETAINED_BYTES=len(self.retained),
                         WIRE_BYTES=len(self.wire), FINAL_BYTES=4))

    def test_fragmented_frames_and_magic_in_image(self):
        for width in (1, 13, len(self.wire)):
            with self.subTest(width=width):
                output = io.BytesIO()
                reader = capture.SweepCapture()
                for offset in range(0, len(self.wire), width):
                    reader.feed(self.wire[offset:offset+width], output)
                receipt = reader.finish()
                self.assertEqual(output.getvalue(), self.retained)
                self.assertEqual(receipt['wire_sha256'], hashlib.sha256(self.wire).hexdigest())
                self.assertEqual(receipt['retained_sha256'], hashlib.sha256(self.retained).hexdigest())
                self.assertEqual(receipt['frames'], [
                    {'sweep': sweep, 'slot': sweep%2, 'bytes': 11, 'sha256': hashlib.sha256(image).hexdigest()}
                    for sweep, image in enumerate((self.first_image, self.second_image), 1)])

    def test_wrong_epoch_truncation_and_trailing_data_fail(self):
        for header in (self.second_header, capture.FRAME.pack(capture.MAGIC, 1, 0, 11),
                       capture.FRAME.pack(capture.MAGIC, 1, 1, 12), b'X'+self.first_header[1:]):
            with self.assertRaisesRegex(ValueError, 'frame identity'):
                capture.SweepCapture().feed(self.wire.replace(self.first_header, header), io.BytesIO())
        for end in (13, 50, len(self.wire)-1):
            reader = capture.SweepCapture()
            reader.feed(self.wire[:end], io.BytesIO())
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                reader.finish()
        with self.assertRaisesRegex(ValueError, 'admitted extent'):
            capture.SweepCapture().feed(self.wire+b'x', io.BytesIO())

    def test_child_receipt_separates_transient_and_retained_bytes(self):
        with TemporaryDirectory() as temporary:
            for exit_code in (0, 2):
                output = Path(temporary)/str(exit_code)
                command = [sys.executable, '-B', '-c',
                           f'import sys;sys.stdout.buffer.write(bytes.fromhex({self.wire.hex()!r}));sys.exit({exit_code})']
                result = run_bounded_dyadic_probe(command, 'TRAIN_TEN_SWEEP_STREAM', output)
                self.assertEqual((output/'stdout.bin').read_bytes(), self.retained)
                self.assertEqual(result['streams'][0]['observed_bytes'], len(self.wire))
                self.assertEqual(result['streams'][0]['saved_bytes'], len(self.retained))
                if exit_code == 0:
                    require_exit(result, output)
                else:
                    with self.assertRaises(ValueError):
                        require_exit(result, output)


class BoundedProof9CaptureTests(unittest.TestCase):
    def test_reused_slots_keep_all_generation_digests(self):
        for sweeps, retained, wire in ((3,2_579_724,17_141_340),(4,3_045_420,22_460_908)):
            with self.subTest(sweeps=sweeps):
                self.check_reused_slots(sweeps,retained,wire)

    def check_reused_slots(self, sweeps, retained, wire):
        reader = capture.SweepCapture(proof9_sweeps=sweeps)
        output = io.BytesIO()
        hashes = []
        for kind, extent in reader.segments:
            if kind == 'header':
                sweep = len(hashes)+1
                reader.feed(capture.FRAME.pack(capture.MAGIC,sweep,sweep%2,reader.image_bytes),output)
                continue
            byte = bytes([65+len(hashes)]) if kind=='image' else b'N'
            digest = hashlib.sha256()
            remaining = extent
            while remaining:
                chunk = byte*min(32768,remaining)
                reader.feed(chunk,output)
                digest.update(chunk)
                remaining -= len(chunk)
            if kind=='image':
                hashes.append(digest.hexdigest())
        receipt = reader.finish()
        self.assertEqual([frame['slot'] for frame in receipt['frames']], [epoch%2 for epoch in range(1,sweeps+1)])
        self.assertEqual([frame['sha256'] for frame in receipt['frames']], hashes)
        self.assertEqual(len(output.getvalue()), retained)
        images = [{'bytes': reader.image_bytes,'sha256': digest} for digest in hashes[-2:]]
        process = {'sweep_capture':receipt,'streams':[{'observed_bytes':wire,'saved_bytes':retained,
                   'sha256':receipt['retained_sha256'],'wire_sha256':receipt['wire_sha256']}]}
        admission = {'sweep_stream':reader.contract}
        self.assertEqual(verify_sweep_capture(process,admission,images,receipt['retained_sha256']),receipt)
        with self.assertRaisesRegex(ValueError,'checkpoint bytes or order'):
            verify_sweep_capture(process,admission,images[::-1],receipt['retained_sha256'])
