"""Convert authenticated split-sweep images to seekable lossless pages."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import time

from scripts.dyadic_checkpoint_transport import MAGIC, PageReader, pack_pages
from scripts.verify_virtual_dyadic_training import (
    PACKED_IMAGE_NAMES, SPLIT_IMAGE_BYTES, SPLIT_IMAGE_NAMES, TEN_CARD_IMAGE_BYTES, authenticated_file,
)
from tests.virtual_frozen_saved_review import unlinked_path


def pack_directory(source, output, digests, *, ten_card=False):
    started = time.perf_counter()
    source, output = Path(source), Path(output).absolute()
    digests = tuple(digests)
    raw_bytes = TEN_CARD_IMAGE_BYTES if ten_card else SPLIT_IMAGE_BYTES
    unlinked_path(output.parent)
    records = []
    with ExitStack() as stack:
        inputs = [stack.enter_context(authenticated_file(source / name, digest, raw_bytes, private=True))
                  for name, digest in zip(SPLIT_IMAGE_NAMES, digests, strict=True)]
        if len({(info.st_dev, info.st_ino) for _, info in inputs}) != len(SPLIT_IMAGE_NAMES):
            raise ValueError('raw checkpoint inputs alias')
        output.mkdir()
        for (stream, _), raw_name, packed_name, expected in zip(
            inputs, SPLIT_IMAGE_NAMES, PACKED_IMAGE_NAMES, digests, strict=True
        ):
            with (output / packed_name).open('x+b') as packed:
                if pack_pages(stream, packed, raw_bytes) != expected:
                    raise ValueError('raw checkpoint changed during encoding')
                packed.flush()
                size = os.fstat(packed.fileno()).st_size
                pages = PageReader(packed, raw_bytes, size)
                if pages.decoded_sha256() != expected:
                    raise ValueError('packed checkpoint round trip differs')
                packed.seek(0)
                digest = hashlib.file_digest(packed, 'sha256').hexdigest()
            records.append({'raw': {'name': raw_name, 'bytes': raw_bytes, 'sha256': expected},
                            'packed': {'name': packed_name, 'bytes': size, 'sha256': digest},
                            'pages': pages.pages})
    packet = {'format': MAGIC.decode('ascii'), 'images': records, 'ten_card': ten_card,
              'duration_seconds': time.perf_counter() - started}
    with (output / 'packet.json').open('x', encoding='utf-8') as receipt:
        json.dump(packet, receipt, indent=2, sort_keys=True)
        receipt.write('\n')
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--page-images', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sweep-image-sha256', nargs=2, required=True, metavar=('SWEEP1', 'SWEEP2'))
    parser.add_argument('--ten-card', action='store_true')
    args = parser.parse_args()
    print(json.dumps(pack_directory(args.page_images, args.output, args.sweep_image_sha256,
                                    ten_card=args.ten_card), sort_keys=True))


if __name__ == '__main__':
    main()
