"""Bounded, independently framed pages for immutable dyadic checkpoints."""
from hashlib import sha256
import struct
import zlib


PAGE_BYTES = 4096 * 8
MAX_RAW_BYTES = 2_962_722 * 8
MAGIC = b'OPLPGZ01'
HEADER = struct.Struct('<8sQ')
OFFSET = struct.Struct('<Q')


def page_count(raw_bytes):
    if type(raw_bytes) is not int or not 0 < raw_bytes <= MAX_RAW_BYTES or raw_bytes % 8:
        raise ValueError('invalid packed checkpoint raw extent')
    return (raw_bytes + PAGE_BYTES - 1) // PAGE_BYTES


def packed_ceiling(raw_bytes):
    return HEADER.size + OFFSET.size * (page_count(raw_bytes) + 1) + raw_bytes


def _read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('truncated packed checkpoint')
    return data


def pack_pages(source, destination, raw_bytes):
    """Encode one exact little-endian image and return its decoded SHA-256."""
    pages = page_count(raw_bytes)
    if destination.seek(0, 2):
        raise ValueError('packed checkpoint destination must be empty')
    directory_bytes = OFFSET.size * (pages + 1)
    destination.write(HEADER.pack(MAGIC, raw_bytes))
    destination.write(bytes(directory_bytes))
    directory = bytearray(directory_bytes)
    digest = sha256()
    for index in range(pages):
        OFFSET.pack_into(directory, index * OFFSET.size, destination.tell())
        raw = _read_exact(source, min(PAGE_BYTES, raw_bytes - index * PAGE_BYTES))
        digest.update(raw)
        encoded = zlib.compress(raw, level=6, wbits=-15)
        destination.write(encoded if len(encoded) < len(raw) else raw)
    if source.read(1):
        raise ValueError('trailing raw checkpoint data')
    end = destination.tell()
    OFFSET.pack_into(directory, pages * OFFSET.size, end)
    destination.seek(HEADER.size)
    destination.write(directory)
    destination.seek(end)
    return digest.hexdigest()


class PageReader:
    """Read exact bytes with a bounded index and at most one cached page."""

    def __init__(self, stream, raw_bytes, packed_bytes):
        self.pages = page_count(raw_bytes)
        self.raw_bytes = raw_bytes
        directory_bytes = OFFSET.size * (self.pages + 1)
        first = HEADER.size + directory_bytes
        if not first < packed_bytes <= packed_ceiling(raw_bytes):
            raise ValueError('packed checkpoint extent exceeds allowance')
        if stream.seek(0, 2) != packed_bytes:
            raise ValueError('packed checkpoint extent differs')
        stream.seek(0)
        if HEADER.unpack(_read_exact(stream, HEADER.size)) != (MAGIC, raw_bytes):
            raise ValueError('packed checkpoint header differs')
        self.directory = _read_exact(stream, directory_bytes)
        if self._offset(0) != first or self._offset(self.pages) != packed_bytes:
            raise ValueError('packed checkpoint directory endpoints differ')
        for index in range(self.pages):
            length = self._offset(index + 1) - self._offset(index)
            if not 0 < length <= self._page_size(index):
                raise ValueError('invalid packed checkpoint page extent')
        self.stream = stream
        self.position = 0
        self.cached_index = -1
        self.cached_page = b''

    def _offset(self, index):
        return OFFSET.unpack_from(self.directory, index * OFFSET.size)[0]

    def _page_size(self, index):
        return min(PAGE_BYTES, self.raw_bytes - index * PAGE_BYTES)

    def read_page(self, index):
        if type(index) is not int or not 0 <= index < self.pages:
            raise ValueError('packed checkpoint page outside bounds')
        if index == self.cached_index:
            return self.cached_page
        expected = self._page_size(index)
        offset = self._offset(index)
        self.stream.seek(offset)
        frame = _read_exact(self.stream, self._offset(index + 1) - offset)
        if len(frame) == expected:
            raw = frame
        else:
            decoder = zlib.decompressobj(wbits=-15)
            try:
                raw = decoder.decompress(frame, expected + 1)
            except zlib.error as exc:
                raise ValueError('invalid packed checkpoint page') from exc
            if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise ValueError('invalid packed checkpoint decoded extent')
        self.cached_index, self.cached_page = index, raw
        return raw

    def read(self, size):
        if type(size) is not int or not 0 <= size <= PAGE_BYTES:
            raise ValueError('packed checkpoint read exceeds one page')
        size = min(size, self.raw_bytes - self.position)
        if not size:
            return b''
        index, offset = divmod(self.position, PAGE_BYTES)
        first = self.read_page(index)[offset:offset + size]
        data = first if len(first) == size else first + self.read_page(index + 1)[:size - len(first)]
        self.position += size
        return data

    def decoded_sha256(self):
        self.cached_index, self.cached_page = -1, b''
        digest = sha256()
        for index in range(self.pages):
            digest.update(self.read_page(index))
        # Replay re-reads every frame, including a one-page image.
        self.cached_index, self.cached_page = -1, b''
        return digest.hexdigest()
