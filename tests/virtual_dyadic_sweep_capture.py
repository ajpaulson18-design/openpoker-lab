"""Demultiplex named native sweep streams without saving image bodies."""
import hashlib
import struct


FRAME = struct.Struct('<8sQQQ')
MAGIC = b'OPLCPG01'
PRELUDE_BYTES = 8 + 16*8 + 11*8 + 1105*96 + 119196*24
PROFILE_AND_ROOT_BYTES = 281066*8 + 4*12*8
IMAGE_BYTES = 23_701_776
RETAINED_BYTES = 9_833_076
WIRE_BYTES = RETAINED_BYTES + 2*(FRAME.size + IMAGE_BYTES)
FINAL_BYTES = RETAINED_BYTES - PRELUDE_BYTES - 2*PROFILE_AND_ROOT_BYTES
SCRATCH_BYTES = 32768


def sweep_stream_contract(*, proof9_t3=False):
    frames, image_bytes, retained, wire = ((3, 4_853_840, 2_579_724, 17_141_340)
                                          if proof9_t3 else (2, IMAGE_BYTES, RETAINED_BYTES, WIRE_BYTES))
    blocks = (image_bytes+SCRATCH_BYTES-1)//SCRATCH_BYTES
    return {'version': 1, 'frames': frames, 'frame_header_bytes': FRAME.size,
            'image_bytes': image_bytes, 'wire_bytes': wire,
            'retained_bytes': retained, 'read_bytes': frames*image_bytes,
            'scratch_bytes': SCRATCH_BYTES,
            'copy_work': frames*(2*(image_bytes//8) + 64*blocks + FRAME.size)}


class SweepCapture:
    """Use admitted offsets so magic bytes in image data are ordinary bytes."""
    def __init__(self, *, proof9_t3=False):
        self.contract = sweep_stream_contract(proof9_t3=proof9_t3)
        count = self.contract['frames']
        self.image_bytes = self.contract['image_bytes']
        if proof9_t3:
            prelude = 8 + 16*8 + 11*8 + 1105*96 + 24420*24
            profile_and_roots = 58164*8 + 4*12*8
            final = self.contract['retained_bytes'] - prelude - count*profile_and_roots
        else:
            prelude, profile_and_roots, final = PRELUDE_BYTES, PROFILE_AND_ROOT_BYTES, FINAL_BYTES
        self.segments = [('numeric', prelude)]
        for _ in range(count):
            self.segments.extend((('numeric', profile_and_roots),
                                  ('header', FRAME.size), ('image', self.image_bytes)))
        self.segments.append(('numeric', final))
        self.index = self.consumed = self.retained = 0
        self.remaining = self.segments[0][1]
        self.header = bytearray()
        self.image_hash = hashlib.sha256()
        self.numeric_hash = hashlib.sha256()
        self.wire_hash = hashlib.sha256()
        self.frames = []

    def feed(self, block, output):
        if len(block) > self.contract['wire_bytes'] - self.consumed:
            raise ValueError('sweep stream exceeds admitted extent')
        self.wire_hash.update(block)
        self.consumed += len(block)
        view = memoryview(block)
        while view:
            kind, _ = self.segments[self.index]
            take = min(len(view), self.remaining)
            part, view = view[:take], view[take:]
            if kind == 'numeric':
                if output.write(part) != take:
                    raise OSError('short saved numerical stream write')
                self.numeric_hash.update(part)
                self.retained += take
            elif kind == 'header':
                self.header.extend(part)
            else:
                self.image_hash.update(part)
            self.remaining -= take
            if self.remaining:
                continue
            sweep = len(self.frames) + 1
            if kind == 'header':
                if FRAME.unpack(self.header) != (MAGIC, sweep, sweep % 2, self.image_bytes):
                    raise ValueError('sweep checkpoint frame identity differs')
                self.header.clear()
            elif kind == 'image':
                self.frames.append({'sweep': sweep, 'slot': sweep % 2, 'bytes': self.image_bytes,
                                    'sha256': self.image_hash.hexdigest()})
                self.image_hash = hashlib.sha256()
            self.index += 1
            if self.index < len(self.segments):
                self.remaining = self.segments[self.index][1]

    def finish(self):
        if (self.consumed, self.retained, self.index, len(self.frames)) != (
                self.contract['wire_bytes'], self.contract['retained_bytes'], len(self.segments), self.contract['frames']):
            raise ValueError('incomplete sweep checkpoint stream')
        return {'contract': self.contract, 'frames': self.frames,
                'wire_sha256': self.wire_hash.hexdigest(),
                'retained_sha256': self.numeric_hash.hexdigest()}
