"""Adversarial image/map correspondence and proven-extent controls."""
import io
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts.verify_native_public_map import (
    Image, bind_public_map, bounded_read, locate_public_function, verify_correspondence)

def image(stamp=123):
    raw = bytearray(2560)
    raw[:2] = b"MZ"
    struct.pack_into("<I", raw, 0x3c, 128)
    raw[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", raw, 132, 0x8664, 3, stamp, 0, 0, 240, 0x22)
    op = 152
    struct.pack_into("<H", raw, op, 0x20b)
    struct.pack_into("<I", raw, op+16, 0x1000)
    struct.pack_into("<Q", raw, op+24, 0x140000000)
    struct.pack_into("<II", raw, op+32, 4096, 512)
    struct.pack_into("<II", raw, op+56, 16384, 512)
    struct.pack_into("<I", raw, op+108, 16)
    struct.pack_into("<II", raw, op+112+3*8, 0x3000, 24)
    struct.pack_into("<II", raw, op+112+6*8, 0x2000, 28)
    for i,(name,vs,rva,rs,rp,flags) in enumerate((
        (b".text",256,0x1000,512,512,0x60000020),
        (b".rdata",1024,0x2000,1024,1024,0x40000040),
        (b".pdata",24,0x3000,512,2048,0x40000040))):
        p = op+240+40*i
        raw[p:p+8] = name.ljust(8,b"\0")
        struct.pack_into("<IIII",raw,p+8,vs,rva,rs,rp)
        struct.pack_into("<I",raw,p+36,flags)
    raw[512:768] = b"\x90"*256
    struct.pack_into("<IIHHIIII",raw,1024,0,stamp,0,0,13,16,0x2200,1536)
    struct.pack_into("<IIIIII",raw,2048,0x1000,0x1080,0x2100,0x1080,0x1100,0x2104)
    return bytes(raw)

def public_map():
    return b""" example
 Preferred load address is 0000000140000000
 Address         Publics by Value              Rva+Base               Lib:Object
 0001:00000000 ?first 0000000140001000 f i sample.obj
 0001:00000000 ?folded_alias 0000000140001000 f i sample.obj
 0001:000000c0 ?leaf_without_extent 00000001400010c0 f sample.obj
 0002:00000080 ?data 0000000140002080 sample.obj
 entry point at 0001:00000000
 Static symbols
"""

def replace(raw, offset, data):
    value = bytearray(raw)
    value[offset:offset+len(data)] = data
    return bytes(value)

class NativePublicMapTests(unittest.TestCase):
    def test_full_bytes_match_after_only_derived_timestamp_masks(self):
        record = verify_correspondence(image(123), image(456))
        self.assertEqual(record["timestamp_ranges"], [[136,140],[1028,1032]])
        self.assertEqual(record["original_timestamp"],123)
        self.assertEqual(record["mapped_timestamp"],456)
        self.assertTrue(set(record["differing_offsets"]) <= {136,137,138,139,1028,1029,1030,1031})
        self.assertNotEqual(record["original_sha256"],record["mapped_sha256"])
        self.assertEqual(verify_correspondence(image(),image())["differing_offsets"],[])

    def test_code_constant_unwind_and_padding_drift_are_rejected(self):
        for offset in (512,1100,2048,2559):
            with self.subTest(offset=offset):
                changed=replace(image(456),offset,bytes([image(456)[offset]^1]))
                with self.assertRaises(ValueError):
                    verify_correspondence(image(),changed)

    def test_debug_type_stamp_count_and_mutable_metadata_fail(self):
        cases=(
            replace(image(),1028,struct.pack("<I",999)),
            replace(image(),1036,struct.pack("<I",2)),
            replace(image(),152+112+6*8+4,struct.pack("<I",56)),
            replace(image(),152+240+40+36,struct.pack("<I",0xc0000040)),
            replace(image(),152+240+40+36,struct.pack("<I",0x60000040)),
        )
        for raw in cases:
            with self.subTest(raw_sha=hash(raw)):
                with self.assertRaises(ValueError):
                    Image(raw)

    def test_header_section_and_debug_payload_bounds(self):
        cases=(
            b"MZ",
            replace(image(),128,b"BAD!"),
            replace(image(),132,struct.pack("<H",0x14c)),
            replace(image(),152+108,struct.pack("<I",17)),
            replace(image(),152+240+40+12,struct.pack("<I",0x1080)),
            replace(image(),152+240+40+20,struct.pack("<I",512)),
            replace(image(),1044,struct.pack("<I",0xfffffff0)),
            replace(image(),1048,struct.pack("<I",1537)),
        )
        for i,raw in enumerate(cases):
            with self.subTest(case=i):
                with self.assertRaises(ValueError):
                    Image(raw)

    def test_map_binds_base_entry_rva_and_preserves_folded_aliases(self):
        record=bind_public_map(image(),image(456),public_map())
        self.assertEqual(record["public_symbol_count"],4)
        self.assertEqual(record["public_function_starts"],2)
        self.assertEqual(record["runtime_function_count"],2)
        self.assertEqual(record["public_starts_without_proven_extent"],[0x10c0])
        ranges=record["proven_function_ranges"]
        self.assertEqual(len(ranges),1)
        self.assertEqual((ranges[0]["begin_rva"],ranges[0]["end_rva"]),(0x1000,0x1080))
        self.assertEqual([a["name"] for a in ranges[0]["aliases"]],["?first","?folded_alias"])

    def test_lookup_does_not_extend_nearest_symbol_across_gap(self):
        record=bind_public_map(image(),image(),public_map())
        self.assertIsNotNone(locate_public_function(record,0x107f))
        self.assertIsNone(locate_public_function(record,0x1080))
        self.assertIsNone(locate_public_function(record,0x10d0))
        self.assertIsNone(locate_public_function(record,0))
        self.assertIsNotNone(locate_public_function(record,0x1080,return_address=True))
        with self.assertRaises(ValueError):
            locate_public_function(record,True)
        with self.assertRaises(ValueError):
            locate_public_function(record,0x1000,return_address=1)

    def test_map_malformed_records_wrong_base_entry_and_addresses_reject(self):
        cases=(
            public_map().replace(b"Preferred load address is 0000000140000000",b"Preferred load address is 0000000150000000"),
            public_map().replace(b"entry point at 0001:00000000",b"entry point at 0001:00000001"),
            public_map().replace(b"?first 0000000140001000",b"?first 0000000140001001"),
            public_map().replace(b"0001:00000000 ?first",b"0009:00000000 ?first"),
            public_map().replace(b"?first 0000000140001000",b"malformed_record"),
            public_map().replace(b" Static symbols",b" Address Publics by Value"),
        )
        for i,data in enumerate(cases):
            with self.subTest(case=i):
                with self.assertRaises(ValueError):
                    bind_public_map(image(),image(),data)

    def test_runtime_function_invalid_extent_unwind_overlap_and_census(self):
        cases=(
            replace(image(),2048,struct.pack("<I",0x1081)),
            replace(image(),2056,struct.pack("<I",0x1000)),
            replace(image(),2060,struct.pack("<I",0x1070)),
            replace(image(),152+112+3*8+4,struct.pack("<I",25)),
        )
        for i,data in enumerate(cases):
            with self.subTest(case=i):
                with self.assertRaises(ValueError):
                    Image(data).runtime_functions()

    def test_oversized_file_rejects_before_read(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/"large.bin"
            path.write_bytes(b"123456789")
            with patch.object(Path,"open",side_effect=AssertionError("must not read")):
                with self.assertRaises(ValueError):
                    bounded_read(path,8)

    def test_file_growth_read_is_capped_before_rejection(self):
        class TrackingStream(io.BytesIO):
            requested = []
            def read(self, size=-1):
                self.requested.append(size)
                return super().read(size)
        with TemporaryDirectory() as folder:
            path=Path(folder)/"growth.bin"
            path.write_bytes(b"12345678")
            stream=TrackingStream(b"x"*100)
            with patch.object(Path,"open",return_value=stream):
                with self.assertRaises(ValueError):
                    bounded_read(path,8)
            self.assertEqual(stream.requested,[9])

if __name__=="__main__":
    unittest.main()

