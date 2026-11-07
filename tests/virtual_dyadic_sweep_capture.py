"""Demultiplex the fixed native sweep stream without saving image bodies."""
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


def sweep_stream_contract():
    blocks = (IMAGE_BYTES+SCRATCH_BYTES-1)//SCRATCH_BYTES
    return {'version': 1, 'frames': 2, 'frame_header_bytes': FRAME.size,
            'image_bytes': IMAGE_BYTES, 'wire_bytes': WIRE_BYTES,
            'retained_bytes': RETAINED_BYTES, 'read_bytes': 2*IMAGE_BYTES,
            'scratch_bytes': SCRATCH_BYTES,
            'copy_work': 2*(2*(IMAGE_BYTES//8) + 64*blocks + FRAME.size)}


class SweepCapture:
    """Use admitted offsets so magic bytes in image data are ordinary bytes."""
    def __init__(self):
        self.segments = [('numeric', PRELUDE_BYTES)]
        for _ in range(2):
            self.segments.extend((('numeric', PROFILE_AND_ROOT_BYTES),
                                  ('header', FRAME.size), ('image', IMAGE_BYTES)))
        self.segments.append(('numeric', FINAL_BYTES))
        self.index = self.consumed = self.retained = 0
        self.remaining = self.segments[0][1]
        self.header = bytearray()
        self.image_hash = hashlib.sha256()
        self.numeric_hash = hashlib.sha256()
        self.wire_hash = hashlib.sha256()
        self.frames = []

    def feed(self, block, output):
        if len(block) > WIRE_BYTES - self.consumed:
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
                if FRAME.unpack(self.header) != (MAGIC, sweep, sweep % 2, IMAGE_BYTES):
                    raise ValueError('sweep checkpoint frame identity differs')
                self.header.clear()
            elif kind == 'image':
                self.frames.append({'sweep': sweep, 'slot': sweep % 2, 'bytes': IMAGE_BYTES,
                                    'sha256': self.image_hash.hexdigest()})
                self.image_hash = hashlib.sha256()
            self.index += 1
            if self.index < len(self.segments):
                self.remaining = self.segments[self.index][1]

    def finish(self):
        if (self.consumed, self.retained, self.index, len(self.frames)) != (
                WIRE_BYTES, RETAINED_BYTES, len(self.segments), 2):
            raise ValueError('incomplete sweep checkpoint stream')
        return {'contract': sweep_stream_contract(), 'frames': self.frames,
                'wire_sha256': self.wire_hash.hexdigest(),
                'retained_sha256': self.numeric_hash.hexdigest()}
